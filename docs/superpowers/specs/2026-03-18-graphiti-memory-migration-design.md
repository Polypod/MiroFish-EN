# Spec: Migrate Zep Cloud → Graphiti (Self-Hosted Graph Memory)

**Date:** 2026-03-18
**Status:** Approved

---

## Background

MiroFish-EN uses Zep Cloud as a knowledge-graph memory engine for its LLM-powered simulation and reporting pipeline. Zep Cloud is a managed service. This migration replaces it with **Graphiti** (`graphiti-core`), the open-source library Zep Cloud is built on, running against an existing self-hosted Neo4j instance.

The goal is a **drop-in adapter replacement**: all caller code remains unchanged. Only the Zep-specific service files are replaced with Graphiti-backed equivalents that expose identical Python interfaces.

---

## Scope

### What Zep currently provides (in use)

| Capability | Used in |
| --- | --- |
| Ingest text episodes → auto-extract entities + relationships | `zep_graph_memory_updater.py` |
| Paginate all nodes/edges from a graph partition | `zep_entity_reader.py`, `graph_builder.py`, `zep_tools.py` |
| Filter nodes by entity type label | `zep_entity_reader.py` |
| Semantic search over edges (facts) | `oasis_profile_generator.py`, `zep_tools.py` |
| Semantic search over nodes | `oasis_profile_generator.py`, `zep_tools.py` |
| Get edges for a specific node | `zep_entity_reader.py` |
| Build knowledge graph from uploaded documents | `graph_builder.py` |
| Create/delete named graph partitions | `graph_builder.py` |
| Set ontology (typed entity/edge schemas) | `graph_builder.py` |
| Batch-add episodes | `graph_builder.py` |
| Poll episode processing status | `graph_builder.py` |

### What is NOT in scope

- `ontology_generator.py` — contains only a code-gen string referencing `zep_cloud.external_clients.ontology` (for generated OASIS agent Python scripts). Not a runtime import; not changed in this migration.
- Any frontend changes.
- Any simulation logic changes.

---

## Architecture

### Approach: Replace-in-Place with Shared Client Factory

**New file:** `backend/app/services/graphiti_client.py`

A thread-safe singleton factory that creates and caches a `Graphiti` client instance using a module-level lock. Wired with:

- Neo4j connection (URI, user, password from env)
- LLM client for entity extraction (reuses `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME`)
- Embedding client for LM Studio (`GRAPHITI_EMBED_BASE_URL` / `GRAPHITI_EMBED_MODEL` / `GRAPHITI_EMBED_API_KEY`)

On first call, the factory also runs `asyncio.run(graphiti.build_indices_and_constraints())` to ensure Neo4j indexes exist.

**Modified service files (keep filenames, replace internals):**

| File | Exports preserved (unchanged) |
| --- | --- |
| `services/zep_entity_reader.py` | `ZepEntityReader`, `EntityNode`, `FilteredEntities` |
| `services/zep_graph_memory_updater.py` | `ZepGraphMemoryUpdater`, `ZepGraphMemoryManager`, `AgentActivity` |
| `services/zep_tools.py` | `ZepToolsService`, `SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult` |

**Other modified files:**

| File | Change |
| --- | --- |
| `services/graph_builder.py` | Full replacement — see graph_builder section below |
| `services/oasis_profile_generator.py` | Replace direct `Zep` client + `graph.search()` with Graphiti search |
| `config.py` | Replace `ZEP_API_KEY` with Neo4j + embedding config vars; update `validate()` |
| `pyproject.toml` | Replace `zep-cloud==3.13.0` with `graphiti-core` |
| `.env.example` | Update env var documentation |

**Deleted:**

| File | Reason |
| --- | --- |
| `utils/zep_paging.py` | No longer used after all callers are migrated |

**Callers with zero changes required:**
`simulation_runner.py`, `simulation_manager.py`, `simulation_config_generator.py`, `simulation.py` (API), `report_agent.py`, `report.py` (API), `services/__init__.py`.

---

## Configuration

### New environment variables

```bash
# Neo4j (existing instance)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# LM Studio embedding (Qwen3-Embedding-4B-mxfp8)
GRAPHITI_EMBED_BASE_URL=http://localhost:1234/v1
GRAPHITI_EMBED_MODEL=mlx-community/Qwen3-Embedding-4B-mxfp8
GRAPHITI_EMBED_API_KEY=lm-studio
```

### Removed environment variables

```bash
ZEP_API_KEY  # removed
```

### Reused environment variables

```bash
LLM_API_KEY       # Graphiti uses this for entity extraction LLM
LLM_BASE_URL      # same
LLM_MODEL_NAME    # same
```

### `Config` class changes

- Remove `ZEP_API_KEY` attribute.
- Add `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `GRAPHITI_EMBED_BASE_URL`, `GRAPHITI_EMBED_MODEL`, `GRAPHITI_EMBED_API_KEY` attributes.
- Update `Config.validate()`: replace the `ZEP_API_KEY` check with checks for `NEO4J_URI`, `NEO4J_PASSWORD`, and `GRAPHITI_EMBED_BASE_URL`.

---

## API Mapping

### Concept mapping

| Zep concept | Graphiti equivalent |
| --- | --- |
| `graph_id` | `group_id` (same string value, different parameter name) |
| `EpisodeType.text` | `EpisodeType.text` (same) |
| Node labels (e.g. `["Entity", "Person"]`) | Node labels (same structure in Neo4j) |
| Edge `.fact` | Edge `.fact` (same) |
| Edge `.source_node_uuid` / `.target_node_uuid` | Same |
| Edge `.valid_at` / `.invalid_at` / `.expired_at` | Same temporal fields |

### Method mapping

| Zep SDK call | Graphiti equivalent |
| --- | --- |
| `client.graph.add(graph_id, type="text", data=text)` | `await graphiti.add_episode(name=f"batch_{timestamp}", episode_body=text, source_description="simulation activity log", reference_time=datetime.now(), source=EpisodeType.text, group_id=group_id)` |
| `client.graph.search(query, graph_id, scope="edges", reranker="rrf")` | `await graphiti.search_(query, group_ids=[group_id], num_results=N)` — Graphiti has no reranker; results may differ in ranking order |
| `client.graph.search(query, graph_id, scope="nodes")` | `await graphiti.get_nodes_by_query(query, group_ids=[group_id], num_results=N)` |
| `client.graph.node.get_by_graph_id(graph_id, ...)` | Cypher via `graphiti.driver` — see Bulk Retrieval section |
| `client.graph.edge.get_by_graph_id(graph_id, ...)` | Cypher via `graphiti.driver` — see Bulk Retrieval section |
| `client.graph.node.get_entity_edges(node_uuid)` | Cypher: `MATCH (n {uuid: $uuid})-[r:RELATES_TO]-() RETURN r` |
| `client.graph.node.get(uuid_)` | Cypher: `MATCH (n:Entity {uuid: $uuid}) RETURN n LIMIT 1` |

**Key difference on `add_episode`:** `group_id` is a plain string (not a list) for ingestion. The search methods use `group_ids` as a list. These are different parameters.

### Bulk node/edge retrieval (replaces `zep_paging.py`)

Graphiti has no paginated list-all API. All bulk retrieval uses Cypher through `graphiti.driver.execute_query()`. Keyset pagination is used (not SKIP) to avoid full-scan cost on large graphs.

**All nodes for a group:**

```cypher
MATCH (n:Entity)
WHERE $group_id IN n.group_ids
  AND ($cursor IS NULL OR n.uuid > $cursor)
RETURN n
ORDER BY n.uuid
LIMIT $page_size
```

**All edges for a group:**

```cypher
MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
WHERE $group_id IN r.group_ids
  AND ($cursor IS NULL OR r.uuid > $cursor)
RETURN r, s.uuid AS source_uuid, t.uuid AS target_uuid
ORDER BY r.uuid
LIMIT $page_size
```

These replace `fetch_all_nodes()` / `fetch_all_edges()` from `zep_paging.py` in all locations: `zep_entity_reader.py`, `zep_tools.py`, and `graph_builder.py`.

### Async bridging

Graphiti's public API is `async`. Flask is synchronous. Each adapter method wraps async calls with `asyncio.run()`. This is always safe in this deployment because:

- Flask request handlers run in synchronous threads with no active event loop.
- The `ZepGraphMemoryUpdater` background worker runs in a daemon thread with no active event loop.
- `oasis_profile_generator.py` runs Graphiti search calls inside `ThreadPoolExecutor` worker threads, which also have no event loop — `asyncio.run()` is safe there too.

Do not use `loop.run_until_complete()` as a fallback; calling it from a thread with a running loop raises `RuntimeError`. `asyncio.run()` is correct and sufficient for all cases here.

---

## `graph_builder.py` — Detailed Replacement Plan

`GraphBuilderService` has several methods that have no direct Graphiti equivalent. Each is handled as follows.

### `create_graph(name) → str`

**Zep:** Calls `client.graph.create(graph_id, name, description)`.

**Graphiti:** No graph-creation API. Graphs are implicit — they exist when data is written with a `group_id`. `create_graph()` generates the `group_id` UUID locally and returns it immediately. The existing `graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"` line is kept; the `client.graph.create(...)` call is removed.

### `set_ontology(graph_id, ontology)`

**Zep:** Dynamically builds `EntityModel`/`EdgeModel` classes and calls `client.graph.set_ontology()`.

**Graphiti:** Has no ontology API. Entity types are extracted automatically from text by the LLM. `set_ontology()` becomes a **no-op** — logs a warning that ontology pre-configuration is not supported and returns immediately. Graphiti's LLM-based extraction will derive similar entity types from the ingested text.

### `add_text_batches(graph_id, chunks, batch_size, progress_callback) → List[str]`

**Zep:** Uses `client.graph.add_batch(episodes=[EpisodeData(...)])` which returns episode UUIDs.

**Graphiti:** Has no batch-add API. Each chunk is added individually via `asyncio.run(graphiti.add_episode(...))`. The method still iterates in `batch_size` groups for progress reporting and pacing, calling `add_episode` per chunk. Returns an empty list (no UUID needed for polling).

### `_wait_for_episodes(episode_uuids, ...)`

**Zep:** Polls `client.graph.episode.get(uuid_)` checking `.processed`.

**Graphiti:** Has no episode-polling API. `add_episode` is synchronous from the caller's perspective (processing happens before it returns). This method becomes a **no-op** that immediately calls `progress_callback("Processing complete", 1.0)`.

### `_get_graph_info(graph_id) → GraphInfo`

**Zep:** Uses `fetch_all_nodes` / `fetch_all_edges`.

**Graphiti:** Uses the Cypher queries described in the Bulk Retrieval section above.

### `get_graph_data(graph_id) → Dict`

**Zep:** Uses `fetch_all_nodes` / `fetch_all_edges`.

**Graphiti:** Same Cypher approach. Edge `.episodes` field is dropped (Graphiti edges have no episode backlink).

### `delete_graph(graph_id)`

**Zep:** Calls `client.graph.delete(graph_id)`.

**Graphiti:** No delete-graph API. Implemented via two Cypher statements:

```cypher
MATCH (n:Entity) WHERE $group_id IN n.group_ids DETACH DELETE n
```

```cypher
MATCH ()-[r:RELATES_TO]->() WHERE $group_id IN r.group_ids DELETE r
```

---

## Data Flow

### Episode ingestion (ZepGraphMemoryUpdater)

```text
Simulation action log
  → AgentActivity.to_episode_text()
  → batch combined text
  → asyncio.run(graphiti.add_episode(group_id=graph_id, name=f"batch_{ts}", ...))
  → Graphiti extracts entities/relationships via LLM
  → Stores nodes + edges in Neo4j
```

### Entity reading (ZepEntityReader)

```text
graph_id
  → Cypher (keyset paginated): fetch all nodes with group_id
  → Cypher (keyset paginated): fetch all edges with group_id
  → filter by entity label type
  → enrich with related edges/nodes
  → return FilteredEntities
```

### Search / retrieval (ZepToolsService, OasisProfileGenerator)

```text
query + graph_id
  → asyncio.run(graphiti.search_(..., group_ids=[graph_id]))        → edges/facts
  → asyncio.run(graphiti.get_nodes_by_query(..., group_ids=[...]))  → nodes
  → map to SearchResult / NodeInfo / EdgeInfo dataclasses
  → return to caller
```

Note: `oasis_profile_generator.py` runs these two calls in parallel via `ThreadPoolExecutor`. `asyncio.run()` inside a `ThreadPoolExecutor` thread is safe (threads have no event loop).

### Document graph building (GraphBuilderService)

```text
text chunks
  → create_graph() → generate group_id locally (no API call)
  → set_ontology() → no-op (logged)
  → add_text_batches(): loop per chunk → asyncio.run(graphiti.add_episode(..., group_id))
  → _wait_for_episodes() → no-op (processing is sync inside add_episode)
  → _get_graph_info() → Cypher count nodes/edges
```

---

## Error Handling

- Retry logic in `ZepGraphMemoryUpdater` and `ZepEntityReader` is preserved (exponential backoff, 3 attempts).
- `OasisProfileGenerator` retries with the same pattern; falls back gracefully if Graphiti is unavailable.
- `graphiti_client.py` raises `RuntimeError` on init failure with a clear message listing which env vars are missing.
- The singleton uses a `threading.Lock` to prevent race conditions during first initialization in multi-threaded Flask.

---

## Dependencies

```toml
# Remove:
"zep-cloud==3.13.0"

# Add:
"graphiti-core>=0.3"
```

Graphiti-core brings in: `neo4j`, `openai` (for OpenAI-compatible clients), `pydantic`.

---

## Testing Notes

- After migration, `graphiti_client.py` calls `build_indices_and_constraints()` once on first initialization. Confirm no errors on startup.
- Ingest a test episode and confirm entity nodes appear in Neo4j Browser under the expected `group_id`.
- Run a test search query and confirm edges/facts are returned.
- Build a document graph and confirm `create_graph` → `add_text_batches` → `_get_graph_info` returns non-zero counts.
- No automated tests are added in this migration (existing test coverage unchanged).
