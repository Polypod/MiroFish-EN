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
|---|---|
| Ingest text episodes → auto-extract entities + relationships | `zep_graph_memory_updater.py` |
| Paginate all nodes/edges from a graph partition | `zep_entity_reader.py`, `graph_builder.py` |
| Filter nodes by entity type label | `zep_entity_reader.py` |
| Semantic search over edges (facts) | `oasis_profile_generator.py`, `zep_tools.py` |
| Semantic search over nodes | `oasis_profile_generator.py`, `zep_tools.py` |
| Get edges for a specific node | `zep_entity_reader.py` |
| Build knowledge graph from uploaded documents | `graph_builder.py` |

### What is NOT in scope

- `ontology_generator.py` — contains only a code-gen string referencing `zep_cloud.external_clients.ontology` (for generated OASIS agent Python scripts). This is a separate concern and is not changed in this migration.
- Any frontend changes.
- Any simulation logic changes.

---

## Architecture

### Approach: Replace-in-Place with Shared Client Factory

**New file:** `backend/app/services/graphiti_client.py`
A singleton factory that creates and caches a `Graphiti` client instance, wired with:
- Neo4j connection (URI, user, password from env)
- LLM client for entity extraction (reuses `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME`)
- Embedding client for LM Studio (`GRAPHITI_EMBED_BASE_URL` / `GRAPHITI_EMBED_MODEL` / `GRAPHITI_EMBED_API_KEY`)

**Modified service files (keep filenames, replace internals):**

| File | Exports preserved (unchanged) |
|---|---|
| `services/zep_entity_reader.py` | `ZepEntityReader`, `EntityNode`, `FilteredEntities` |
| `services/zep_graph_memory_updater.py` | `ZepGraphMemoryUpdater`, `ZepGraphMemoryManager`, `AgentActivity` |
| `services/zep_tools.py` | `ZepToolsService`, `SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult` |

**Other modified files:**

| File | Change |
|---|---|
| `services/graph_builder.py` | Replace `zep_cloud` imports and `Zep` client with Graphiti |
| `services/oasis_profile_generator.py` | Replace direct `Zep` client + `graph.search()` with Graphiti search |
| `config.py` | Replace `ZEP_API_KEY` with Neo4j + embedding config vars |
| `pyproject.toml` | Replace `zep-cloud==3.13.0` with `graphiti-core` |
| `.env.example` | Update env var documentation |

**Deleted:**

| File | Reason |
|---|---|
| `utils/zep_paging.py` | Graphiti handles pagination internally via Cypher |

**Callers with zero changes required:**
`simulation_runner.py`, `simulation_manager.py`, `simulation_config_generator.py`, `simulation.py` (API), `report_agent.py`, `report.py` (API), `services/__init__.py`.

---

## Configuration

### New environment variables

```
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

```
ZEP_API_KEY  (removed)
```

### Reused environment variables

```
LLM_API_KEY       — Graphiti uses this for entity extraction LLM
LLM_BASE_URL      — same
LLM_MODEL_NAME    — same
```

---

## API Mapping

### Concept mapping

| Zep concept | Graphiti equivalent |
|---|---|
| `graph_id` | `group_id` (same string value, different parameter name) |
| `EpisodeType.text` | `EpisodeType.text` (same) |
| Node labels (e.g. `["Entity", "Person"]`) | Node labels (same structure in Neo4j) |
| Edge `.fact` | Edge `.fact` (same) |
| Edge `.source_node_uuid` / `.target_node_uuid` | Same |
| Edge `.valid_at` / `.invalid_at` / `.expired_at` | Same temporal fields |

### Method mapping

| Zep SDK call | Graphiti equivalent |
|---|---|
| `client.graph.add(graph_id, type="text", data=text)` | `await graphiti.add_episode(name=..., episode_body=text, source_description=..., reference_time=datetime.now(), source=EpisodeType.text, group_ids=[group_id])` |
| `client.graph.search(query, graph_id, scope="edges")` | `await graphiti.search_(query, group_ids=[group_id], num_results=N)` |
| `client.graph.search(query, graph_id, scope="nodes")` | `await graphiti.get_nodes_by_query(query, group_ids=[group_id], num_results=N)` |
| `client.graph.node.get_by_graph_id(graph_id, limit, uuid_cursor)` | Cypher via `graphiti.driver`: `MATCH (n:Entity) WHERE $gid IN n.group_ids RETURN n SKIP $skip LIMIT $limit` |
| `client.graph.edge.get_by_graph_id(graph_id, limit, uuid_cursor)` | Cypher via `graphiti.driver`: `MATCH ()-[r:RELATES_TO]->() WHERE $gid IN r.group_ids RETURN r SKIP $skip LIMIT $limit` |
| `client.graph.node.get_entity_edges(node_uuid)` | Cypher via `graphiti.driver`: `MATCH (n {uuid: $uuid})-[r]-() RETURN r` |
| `client.graph.node.get(uuid_)` | Cypher via `graphiti.driver`: `MATCH (n {uuid: $uuid}) RETURN n` |

### Async bridging

Graphiti's public API is `async`. Flask is synchronous. Each adapter method wraps async calls with `asyncio.run()`. This is safe because:
- Flask request handlers run in synchronous threads with no active event loop.
- The `ZepGraphMemoryUpdater` background worker runs in a daemon thread with no active event loop.

---

## Data Flow

### Episode ingestion (ZepGraphMemoryUpdater)

```
Simulation action log
  → AgentActivity.to_episode_text()
  → batch combined text
  → asyncio.run(graphiti.add_episode(group_id=graph_id, ...))
  → Graphiti extracts entities/relationships via LLM
  → Stores nodes + edges in Neo4j
```

### Entity reading (ZepEntityReader)

```
graph_id
  → Cypher: fetch all nodes with group_id
  → Cypher: fetch all edges with group_id
  → filter by entity label type
  → enrich with related edges/nodes
  → return FilteredEntities
```

### Search / retrieval (ZepToolsService, OasisProfileGenerator)

```
query + graph_id
  → asyncio.run(graphiti.search_(..., group_ids=[graph_id]))     → edges/facts
  → asyncio.run(graphiti.get_nodes_by_query(..., group_ids=[...]))  → nodes
  → map to SearchResult / NodeInfo / EdgeInfo dataclasses
  → return to caller
```

### Document graph building (GraphBuilderService)

```
text chunks
  → asyncio.run(graphiti.add_episode(..., group_id=graph_id))
  → repeated per chunk with delay
  → Cypher: count nodes/edges for result stats
```

---

## Error Handling

- Retry logic in `ZepGraphMemoryUpdater` and `ZepEntityReader` is preserved (exponential backoff, 3 attempts).
- `OasisProfileGenerator` retries with the same pattern; falls back gracefully if Graphiti is unavailable.
- `graphiti_client.py` raises `RuntimeError` on init failure with a clear message listing which env vars are missing.
- All async calls wrapped in `asyncio.run()` — if a running event loop is detected, fall back to `loop.run_until_complete()`.

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

- After migration, verify Neo4j connectivity with `graphiti.build_indices_and_constraints()` on startup.
- Ingest a test episode and confirm entity nodes appear in Neo4j Browser.
- Run a test search query and confirm edges/facts are returned.
- No automated tests are added in this migration (existing test coverage unchanged).
