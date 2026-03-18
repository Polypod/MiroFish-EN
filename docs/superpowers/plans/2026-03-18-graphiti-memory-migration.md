# Graphiti Memory Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Zep Cloud with self-hosted Graphiti (backed by existing Neo4j + LM Studio embeddings) using a drop-in adapter strategy — all caller code unchanged.

**Architecture:** New `graphiti_client.py` singleton factory + `graphiti_cypher.py` bulk-retrieval utilities replace the old `zep_paging.py`. The three core Zep service files are rewritten in-place (same filenames, same exported class names). `graph_builder.py` and `oasis_profile_generator.py` are updated to remove direct Zep SDK calls.

**Tech Stack:** `graphiti-core>=0.3`, `neo4j` (async driver, bundled with graphiti-core), Python `asyncio.run()` for sync/async bridging, `uv` package manager.

---

## File Map

| Action | Path | Purpose |
| --- | --- | --- |
| Create | `backend/app/services/graphiti_client.py` | Thread-safe singleton Graphiti client factory |
| Create | `backend/app/utils/graphiti_cypher.py` | Bulk node/edge fetch via Cypher (replaces zep_paging.py) |
| Rewrite | `backend/app/services/zep_entity_reader.py` | Graphiti-backed entity reader (same exports) |
| Rewrite | `backend/app/services/zep_graph_memory_updater.py` | Graphiti-backed activity updater (same exports) |
| Rewrite | `backend/app/services/zep_tools.py` | Graphiti-backed search tools (same exports) |
| Rewrite | `backend/app/services/graph_builder.py` | Graphiti-backed doc graph builder |
| Modify | `backend/app/services/oasis_profile_generator.py` | Remove direct Zep client |
| Modify | `backend/app/config.py` | Swap Zep config for Neo4j + embedding vars |
| Modify | `backend/pyproject.toml` | Swap zep-cloud for graphiti-core |
| Modify | `.env.example` | Update env var docs |
| Delete | `backend/app/utils/zep_paging.py` | Replaced by graphiti_cypher.py |
| Create | `backend/tests/test_graphiti_client.py` | Unit tests for client factory |
| Create | `backend/tests/test_graphiti_cypher.py` | Unit tests for Cypher helpers |

---

## ⚠️ Schema Verification Required (read before Task 3)

Graphiti stores entity types differently from Zep. After Task 2 (first ingestion), **inspect Neo4j Browser** (`http://localhost:7474`) before writing the entity reader. Check:

1. What Neo4j labels do entity nodes have? (`:EntityNode` only, or `:EntityNode:Person` etc.?)
2. Does each node have a `labels` list property, an `entity_type` string property, or both?
3. Is `group_id` stored as a scalar string or as an array?

Run this in Neo4j Browser after a test ingestion:

```cypher
MATCH (n) RETURN labels(n), n.group_id, keys(n) LIMIT 5
```

The Cypher queries in Tasks 3–4 must be adjusted based on what you find.

---

## Task 1: Swap Dependencies and Update Config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `.env.local` (your actual env file — not committed)

- [ ] **Step 1: Update pyproject.toml**

Replace in `backend/pyproject.toml`:

```toml
# Remove this line:
"zep-cloud==3.13.0",

# Add this line:
"graphiti-core>=0.3",
```

- [ ] **Step 2: Install the new dependency**

```bash
cd backend && uv sync
```

Expected: resolves and installs `graphiti-core` and its deps (`neo4j`, etc.). If `uv sync` conflicts, try `uv add graphiti-core`.

- [ ] **Step 3: Update config.py**

In `backend/app/config.py`, replace the Zep section:

```python
# Remove:
ZEP_API_KEY = os.environ.get('ZEP_API_KEY')

# Add:
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
GRAPHITI_EMBED_BASE_URL = os.environ.get('GRAPHITI_EMBED_BASE_URL', 'http://localhost:1234/v1')
GRAPHITI_EMBED_MODEL = os.environ.get('GRAPHITI_EMBED_MODEL', 'mlx-community/Qwen3-Embedding-4B-mxfp8')
GRAPHITI_EMBED_API_KEY = os.environ.get('GRAPHITI_EMBED_API_KEY', 'lm-studio')
```

Also update `Config.validate()` — replace:

```python
# Remove:
if not cls.ZEP_API_KEY:
    errors.append("ZEP_API_KEY is not configured")

# Add:
if not cls.NEO4J_URI:
    errors.append("NEO4J_URI is not configured")
if not cls.NEO4J_PASSWORD:
    errors.append("NEO4J_PASSWORD is not configured")
if not cls.GRAPHITI_EMBED_BASE_URL:
    errors.append("GRAPHITI_EMBED_BASE_URL is not configured")
```

- [ ] **Step 4: Update .env.example**

Replace the Zep section:

```bash
# ===== Graphiti Memory Graph Configuration =====
# Requires: running Neo4j instance + LM Studio serving an embedding model

# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# LM Studio embedding model (OpenAI-compatible)
GRAPHITI_EMBED_BASE_URL=http://localhost:1234/v1
GRAPHITI_EMBED_MODEL=mlx-community/Qwen3-Embedding-4B-mxfp8
GRAPHITI_EMBED_API_KEY=lm-studio
```

- [ ] **Step 5: Update .env.local with your actual credentials**

Add the new vars (and remove `ZEP_API_KEY`). Keep these values — they're not in the plan.

- [ ] **Step 6: Commit**

```bash
cd ..  # back to project root
git add backend/pyproject.toml backend/uv.lock backend/app/config.py .env.example
git commit -m "feat: swap zep-cloud dependency for graphiti-core, update config"
```

---

## Task 2: Graphiti Client Factory

**Files:**
- Create: `backend/app/services/graphiti_client.py`
- Create: `backend/tests/test_graphiti_client.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_graphiti_client.py`:

```python
"""Unit tests for GraphitiClientFactory."""
import pytest
from unittest.mock import patch, MagicMock


class TestGraphitiClientFactory:
    def test_raises_on_missing_neo4j_password(self):
        """Factory raises RuntimeError if NEO4J_PASSWORD is not set."""
        from backend.app.services.graphiti_client import GraphitiClientFactory
        GraphitiClientFactory._instance = None  # reset singleton

        with patch("backend.app.services.graphiti_client.Config") as mock_cfg:
            mock_cfg.NEO4J_URI = "bolt://localhost:7687"
            mock_cfg.NEO4J_USER = "neo4j"
            mock_cfg.NEO4J_PASSWORD = None
            mock_cfg.GRAPHITI_EMBED_BASE_URL = "http://localhost:1234/v1"
            mock_cfg.GRAPHITI_EMBED_MODEL = "test-model"
            mock_cfg.GRAPHITI_EMBED_API_KEY = "lm-studio"
            mock_cfg.LLM_API_KEY = "sk-test"
            mock_cfg.LLM_BASE_URL = "http://localhost:1234/v1"
            mock_cfg.LLM_MODEL_NAME = "test-llm"

            with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
                GraphitiClientFactory.get_client()

    def test_returns_graphiti_instance_on_valid_config(self):
        """Factory returns a Graphiti instance when config is valid."""
        from backend.app.services.graphiti_client import GraphitiClientFactory
        GraphitiClientFactory._instance = None  # reset singleton

        mock_graphiti = MagicMock()

        with patch("backend.app.services.graphiti_client.Config") as mock_cfg, \
             patch("backend.app.services.graphiti_client.Graphiti", return_value=mock_graphiti), \
             patch("backend.app.services.graphiti_client.asyncio.run"):
            mock_cfg.NEO4J_URI = "bolt://localhost:7687"
            mock_cfg.NEO4J_USER = "neo4j"
            mock_cfg.NEO4J_PASSWORD = "password"
            mock_cfg.GRAPHITI_EMBED_BASE_URL = "http://localhost:1234/v1"
            mock_cfg.GRAPHITI_EMBED_MODEL = "test-model"
            mock_cfg.GRAPHITI_EMBED_API_KEY = "lm-studio"
            mock_cfg.LLM_API_KEY = "sk-test"
            mock_cfg.LLM_BASE_URL = "http://localhost:1234/v1"
            mock_cfg.LLM_MODEL_NAME = "test-llm"

            client = GraphitiClientFactory.get_client()
            assert client is mock_graphiti
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_graphiti_client.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `graphiti_client` doesn't exist yet.

- [ ] **Step 3: Create graphiti_client.py**

Create `backend/app/services/graphiti_client.py`:

```python
"""
Graphiti client factory.
Thread-safe singleton — creates the Graphiti client once and caches it.
"""

import asyncio
import threading

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_client import OpenAIClient, LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.graphiti_client')

_lock = threading.Lock()


class GraphitiClientFactory:
    """Thread-safe singleton factory for the Graphiti client."""

    _instance: Graphiti | None = None

    @classmethod
    def get_client(cls) -> Graphiti:
        """Return the shared Graphiti client, initializing it on first call."""
        if cls._instance is not None:
            return cls._instance

        with _lock:
            if cls._instance is not None:  # double-checked locking
                return cls._instance

            cls._instance = cls._create_client()
            return cls._instance

    @classmethod
    def _create_client(cls) -> Graphiti:
        """Instantiate and initialize the Graphiti client."""
        missing = []
        if not Config.NEO4J_URI:
            missing.append("NEO4J_URI")
        if not Config.NEO4J_PASSWORD:
            missing.append("NEO4J_PASSWORD")
        if not Config.GRAPHITI_EMBED_BASE_URL:
            missing.append("GRAPHITI_EMBED_BASE_URL")
        if missing:
            raise RuntimeError(
                f"Graphiti client cannot initialize — missing config: {', '.join(missing)}"
            )

        llm_client = OpenAIClient(
            config=LLMConfig(
                api_key=Config.LLM_API_KEY,
                model=Config.LLM_MODEL_NAME,
                base_url=Config.LLM_BASE_URL,
            )
        )

        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=Config.GRAPHITI_EMBED_API_KEY,
                embedding_model=Config.GRAPHITI_EMBED_MODEL,
                base_url=Config.GRAPHITI_EMBED_BASE_URL,
            )
        )

        graphiti = Graphiti(
            uri=Config.NEO4J_URI,
            user=Config.NEO4J_USER,
            password=Config.NEO4J_PASSWORD,
            llm_client=llm_client,
            embedder=embedder,
        )

        # Create Neo4j indexes on first init.
        try:
            asyncio.run(graphiti.build_indices_and_constraints())
            logger.info("Graphiti client initialized, Neo4j indexes verified")
        except Exception as e:
            logger.warning(f"Could not build Neo4j indexes (may already exist): {e}")

        return graphiti
```

> **Note:** If `Graphiti(uri=..., user=..., password=...)` is not the correct constructor signature for the installed version, check `python -c "import inspect, graphiti_core; print(inspect.signature(graphiti_core.Graphiti.__init__))"` and adjust accordingly.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_graphiti_client.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Manual smoke test — verify Neo4j connectivity**

Start LM Studio with the embedding model loaded, then:

```bash
cd backend && uv run python -c "
from app.services.graphiti_client import GraphitiClientFactory
client = GraphitiClientFactory.get_client()
print('Client initialized:', type(client).__name__)
"
```

Expected: `Client initialized: Graphiti` (no errors).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/graphiti_client.py backend/tests/test_graphiti_client.py
git commit -m "feat: add Graphiti client singleton factory"
```

---

## Task 3: Graphiti Cypher Utilities (replaces zep_paging.py)

**Files:**
- Create: `backend/app/utils/graphiti_cypher.py`
- Create: `backend/tests/test_graphiti_cypher.py`

> **Before writing these:** Complete the schema verification described at the top of this plan. The Cypher node label (`:EntityNode` vs `:Entity`) and `group_id` storage format must be confirmed first. The code below assumes `:EntityNode` label with `group_id` as a scalar string. Adjust if your inspection shows otherwise.

- [ ] **Step 1: Verify Neo4j schema (manual)**

Ingest one test episode (you can do this after Task 2 is committed, using a quick Python script):

```python
import asyncio
from datetime import datetime, timezone
from graphiti_core.nodes import EpisodeType
from app.services.graphiti_client import GraphitiClientFactory

async def test_ingest():
    g = GraphitiClientFactory.get_client()
    await g.add_episode(
        name="schema_test_001",
        episode_body="Alice is a software engineer at Acme Corp. Bob is Alice's manager.",
        source_description="schema verification test",
        reference_time=datetime.now(timezone.utc),
        source=EpisodeType.text,
        group_id="schema_test_group",
    )
    print("Episode added")

asyncio.run(test_ingest())
```

Then in Neo4j Browser run:

```cypher
MATCH (n) WHERE n.group_id = 'schema_test_group'
RETURN labels(n), n.uuid, n.name, keys(n)
LIMIT 10
```

Note: the actual node label name and property names. Update the Cypher in this task accordingly.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_graphiti_cypher.py`:

```python
"""Unit tests for graphiti_cypher utilities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchAllNodes:
    def test_returns_empty_list_for_empty_graph(self):
        from backend.app.utils.graphiti_cypher import fetch_all_nodes

        mock_driver = MagicMock()
        mock_driver.execute_query = AsyncMock(return_value=([], None, None))

        result = fetch_all_nodes(mock_driver, "test_group")
        assert result == []

    def test_returns_nodes_from_single_page(self):
        from backend.app.utils.graphiti_cypher import fetch_all_nodes

        mock_record = {"uuid": "abc", "name": "Alice", "summary": "A person",
                       "labels_list": ["EntityNode"], "created_at": None}
        mock_driver = MagicMock()
        # First page returns one record, second page returns empty (signals end)
        mock_driver.execute_query = AsyncMock(
            side_effect=[([ mock_record], None, None), ([], None, None)]
        )

        result = fetch_all_nodes(mock_driver, "test_group")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_paginates_across_multiple_pages(self):
        from backend.app.utils.graphiti_cypher import fetch_all_nodes

        page1 = [{"uuid": f"id{i}", "name": f"Node{i}", "summary": "",
                  "labels_list": ["EntityNode"], "created_at": None} for i in range(5)]
        page2 = [{"uuid": f"id{i}", "name": f"Node{i}", "summary": "",
                  "labels_list": ["EntityNode"], "created_at": None} for i in range(5, 8)]
        mock_driver = MagicMock()
        mock_driver.execute_query = AsyncMock(
            side_effect=[(page1, None, None), (page2, None, None), ([], None, None)]
        )

        result = fetch_all_nodes(mock_driver, "test_group", page_size=5)
        assert len(result) == 8
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_graphiti_cypher.py -v
```

Expected: `ImportError` — `graphiti_cypher` doesn't exist yet.

- [ ] **Step 4: Create graphiti_cypher.py**

Create `backend/app/utils/graphiti_cypher.py`:

```python
"""
Graphiti bulk retrieval utilities.

Fetches all nodes/edges for a group using keyset pagination via Neo4j Cypher.
Replaces zep_paging.py.

IMPORTANT: The node label (:EntityNode) and property names below were verified
against the actual Neo4j schema. If the schema differs, update the MATCH clauses.
"""

import asyncio
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger('mirofish.graphiti_cypher')

_DEFAULT_PAGE_SIZE = 100
_MAX_NODES = 2000


# ---------------------------------------------------------------------------
# Internal async helpers
# ---------------------------------------------------------------------------

async def _fetch_nodes_page(
    driver,
    group_id: str,
    cursor: Optional[str],
    page_size: int,
) -> List[Dict[str, Any]]:
    """Fetch one page of entity nodes using keyset pagination."""
    # Adjust `:EntityNode` and `n.group_id` if your schema uses different names.
    cypher = """
    MATCH (n:EntityNode)
    WHERE n.group_id = $group_id
      AND ($cursor IS NULL OR n.uuid > $cursor)
    RETURN n.uuid AS uuid,
           n.name AS name,
           n.summary AS summary,
           labels(n) AS labels_list,
           n.created_at AS created_at
    ORDER BY n.uuid
    LIMIT $page_size
    """
    records, _, _ = await driver.execute_query(
        cypher,
        group_id=group_id,
        cursor=cursor,
        page_size=page_size,
        routing_="r",
    )
    return [dict(r) for r in records]


async def _fetch_edges_page(
    driver,
    group_id: str,
    cursor: Optional[str],
    page_size: int,
) -> List[Dict[str, Any]]:
    """Fetch one page of RELATES_TO edges using keyset pagination."""
    cypher = """
    MATCH (s:EntityNode)-[r:RELATES_TO]->(t:EntityNode)
    WHERE r.group_id = $group_id
      AND ($cursor IS NULL OR r.uuid > $cursor)
    RETURN r.uuid AS uuid,
           r.name AS name,
           r.fact AS fact,
           s.uuid AS source_node_uuid,
           t.uuid AS target_node_uuid,
           r.created_at AS created_at,
           r.valid_at AS valid_at,
           r.invalid_at AS invalid_at,
           r.expired_at AS expired_at
    ORDER BY r.uuid
    LIMIT $page_size
    """
    records, _, _ = await driver.execute_query(
        cypher,
        group_id=group_id,
        cursor=cursor,
        page_size=page_size,
        routing_="r",
    )
    return [dict(r) for r in records]


async def _get_node_by_uuid(driver, node_uuid: str) -> Optional[Dict[str, Any]]:
    cypher = """
    MATCH (n:EntityNode {uuid: $uuid})
    RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
           labels(n) AS labels_list
    LIMIT 1
    """
    records, _, _ = await driver.execute_query(cypher, uuid=node_uuid, routing_="r")
    if not records:
        return None
    return dict(records[0])


async def _get_edges_for_node(driver, node_uuid: str) -> List[Dict[str, Any]]:
    cypher = """
    MATCH (n:EntityNode {uuid: $uuid})-[r:RELATES_TO]-(m:EntityNode)
    RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
           startNode(r).uuid AS source_node_uuid,
           endNode(r).uuid AS target_node_uuid
    """
    records, _, _ = await driver.execute_query(cypher, uuid=node_uuid, routing_="r")
    return [dict(r) for r in records]


# ---------------------------------------------------------------------------
# Public sync API (bridge async → sync with asyncio.run)
# ---------------------------------------------------------------------------

def fetch_all_nodes(
    driver,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_NODES,
) -> List[Dict[str, Any]]:
    """
    Fetch all entity nodes for a group_id.
    Returns list of dicts with keys: uuid, name, summary, labels_list, created_at.
    """
    async def _fetch():
        all_nodes: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            batch = await _fetch_nodes_page(driver, group_id, cursor, page_size)
            if not batch:
                break
            all_nodes.extend(batch)
            if len(all_nodes) >= max_items:
                all_nodes = all_nodes[:max_items]
                logger.warning(f"Node limit ({max_items}) reached for group {group_id}")
                break
            if len(batch) < page_size:
                break
            cursor = batch[-1]["uuid"]
        return all_nodes

    return asyncio.run(_fetch())


def fetch_all_edges(
    driver,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> List[Dict[str, Any]]:
    """
    Fetch all RELATES_TO edges for a group_id.
    Returns list of dicts with edge fields.
    """
    async def _fetch():
        all_edges: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            batch = await _fetch_edges_page(driver, group_id, cursor, page_size)
            if not batch:
                break
            all_edges.extend(batch)
            if len(batch) < page_size:
                break
            cursor = batch[-1]["uuid"]
        return all_edges

    return asyncio.run(_fetch())


def get_node_by_uuid(driver, node_uuid: str) -> Optional[Dict[str, Any]]:
    """Fetch a single node by UUID."""
    return asyncio.run(_get_node_by_uuid(driver, node_uuid))


def get_edges_for_node(driver, node_uuid: str) -> List[Dict[str, Any]]:
    """Fetch all edges connected to a node."""
    return asyncio.run(_get_edges_for_node(driver, node_uuid))


def delete_group(driver, group_id: str) -> None:
    """Delete all nodes and edges for a group_id."""
    async def _delete():
        await driver.execute_query(
            "MATCH (n:EntityNode) WHERE n.group_id = $group_id DETACH DELETE n",
            group_id=group_id,
        )
        await driver.execute_query(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $group_id DELETE r",
            group_id=group_id,
        )
    asyncio.run(_delete())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_graphiti_cypher.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/utils/graphiti_cypher.py backend/tests/test_graphiti_cypher.py
git commit -m "feat: add Graphiti Cypher utilities (replaces zep_paging.py)"
```

---

## Task 4: Migrate zep_entity_reader.py

**Files:**
- Modify: `backend/app/services/zep_entity_reader.py` (rewrite internals, keep all exports)

The exported types `ZepEntityReader`, `EntityNode`, `FilteredEntities` must remain identical — all callers import them.

> **Note on entity labels:** The `filter_defined_entities` method filters nodes whose `labels` include a non-default type. Graphiti may store entity types differently from Zep. After your schema verification (Task 3, Step 1), you may need to adjust the filtering logic. Two possibilities:
> - If Graphiti adds type labels as actual Neo4j labels (`:EntityNode:Person`), use `labels_list` from the Cypher `labels(n)` return.
> - If Graphiti stores types in a `name` property or `entity_type` property, filter on that instead.
>
> The code below uses `labels_list` (from `labels(n)` Cypher). Adjust as needed.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_graphiti_entity_reader.py`:

```python
"""Unit tests for ZepEntityReader (Graphiti-backed)."""
import pytest
from unittest.mock import MagicMock, patch


def _make_node(uuid, name, labels, summary="", attributes=None):
    return {
        "uuid": uuid,
        "name": name,
        "labels_list": labels,
        "summary": summary,
        "attributes": attributes or {},
        "created_at": None,
    }


def _make_edge(uuid, name, fact, src, tgt):
    return {
        "uuid": uuid,
        "name": name,
        "fact": fact,
        "source_node_uuid": src,
        "target_node_uuid": tgt,
        "created_at": None,
        "valid_at": None,
        "invalid_at": None,
        "expired_at": None,
    }


class TestZepEntityReader:
    def _make_reader(self, mock_driver):
        with patch("backend.app.services.zep_entity_reader.GraphitiClientFactory") as mock_factory:
            mock_graphiti = MagicMock()
            mock_graphiti.driver = mock_driver
            mock_factory.get_client.return_value = mock_graphiti
            from backend.app.services.zep_entity_reader import ZepEntityReader
            return ZepEntityReader()

    def test_filter_defined_entities_skips_plain_entity_nodes(self):
        """Nodes with only default labels are excluded."""
        mock_driver = MagicMock()

        with patch("backend.app.services.zep_entity_reader.fetch_all_nodes") as mock_nodes, \
             patch("backend.app.services.zep_entity_reader.fetch_all_edges") as mock_edges, \
             patch("backend.app.services.zep_entity_reader.GraphitiClientFactory") as mock_factory:

            mock_graphiti = MagicMock()
            mock_factory.get_client.return_value = mock_graphiti

            mock_nodes.return_value = [
                _make_node("1", "Generic", ["EntityNode"]),
                _make_node("2", "Alice", ["EntityNode", "Person"]),
            ]
            mock_edges.return_value = []

            from backend.app.services.zep_entity_reader import ZepEntityReader
            reader = ZepEntityReader()
            result = reader.filter_defined_entities("test_graph")

        assert result.total_count == 2
        assert result.filtered_count == 1
        assert result.entities[0].name == "Alice"

    def test_entity_node_get_entity_type(self):
        """EntityNode.get_entity_type() returns the first non-default label."""
        from backend.app.services.zep_entity_reader import EntityNode
        node = EntityNode(
            uuid="x", name="Bob", labels=["EntityNode", "Organization"],
            summary="", attributes={}
        )
        assert node.get_entity_type() == "Organization"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_graphiti_entity_reader.py -v
```

Expected: tests fail (old Zep imports still present).

- [ ] **Step 3: Rewrite zep_entity_reader.py**

Replace the entire file content. Keep all existing dataclasses (`EntityNode`, `FilteredEntities`) and all public method signatures on `ZepEntityReader`. Only replace the internals:

```python
"""
Graphiti entity read and filter service.
Reads nodes from a Graphiti graph and filters nodes by entity type.

Drop-in replacement for the former Zep-based implementation.
Exports: ZepEntityReader, EntityNode, FilteredEntities (unchanged)
"""

import time
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from ..utils.graphiti_cypher import (
    fetch_all_nodes,
    fetch_all_edges,
    get_node_by_uuid,
    get_edges_for_node,
)
from .graphiti_client import GraphitiClientFactory

logger = get_logger('mirofish.zep_entity_reader')
T = TypeVar('T')

# Labels that are default/infrastructure — not entity types.
_DEFAULT_LABELS = {"EntityNode", "Entity", "Node"}


@dataclass
class EntityNode:
    """Entity node data structure."""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        for label in self.labels:
            if label not in _DEFAULT_LABELS:
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity collection."""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Graphiti-backed entity reader.
    Interface identical to the former ZepEntityReader.
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key parameter kept for interface compatibility; unused with Graphiti.
        self._graphiti = GraphitiClientFactory.get_client()
        self._driver = self._graphiti.driver

    def _call_with_retry(
        self,
        func: Callable[[], T],
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0,
    ) -> T:
        last_exception = None
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Graphiti {operation_name} attempt {attempt+1} failed: "
                        f"{str(e)[:100]}, retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(
                        f"Graphiti {operation_name} failed after {max_retries} attempts: {e}"
                    )
        raise last_exception

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"Fetching all nodes for group {graph_id}...")
        raw = fetch_all_nodes(self._driver, graph_id)
        nodes = []
        for r in raw:
            nodes.append({
                "uuid": r.get("uuid", ""),
                "name": r.get("name", ""),
                "labels": r.get("labels_list", []),
                "summary": r.get("summary", ""),
                "attributes": r.get("attributes", {}),
            })
        logger.info(f"Fetched {len(nodes)} nodes")
        return nodes

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"Fetching all edges for group {graph_id}...")
        raw = fetch_all_edges(self._driver, graph_id)
        edges = []
        for r in raw:
            edges.append({
                "uuid": r.get("uuid", ""),
                "name": r.get("name", ""),
                "fact": r.get("fact", ""),
                "source_node_uuid": r.get("source_node_uuid", ""),
                "target_node_uuid": r.get("target_node_uuid", ""),
                "attributes": {},
            })
        logger.info(f"Fetched {len(edges)} edges")
        return edges

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        try:
            raw = self._call_with_retry(
                func=lambda: get_edges_for_node(self._driver, node_uuid),
                operation_name=f"get node edges (node={node_uuid[:8]}...)",
            )
            return [
                {
                    "uuid": r.get("uuid", ""),
                    "name": r.get("name", ""),
                    "fact": r.get("fact", ""),
                    "source_node_uuid": r.get("source_node_uuid", ""),
                    "target_node_uuid": r.get("target_node_uuid", ""),
                    "attributes": {},
                }
                for r in raw
            ]
        except Exception as e:
            logger.warning(f"Failed to get edges for node {node_uuid}: {e}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        logger.info(f"Filtering entities for group {graph_id}...")
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {n["uuid"]: n for n in all_nodes}

        filtered_entities = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in _DEFAULT_LABELS]
            if not custom_labels:
                continue
            if defined_entity_types:
                matching = [l for l in custom_labels if l in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]
            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node.get("attributes", {}),
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids: Set[str] = set()
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                entity.related_edges = related_edges
                entity.related_nodes = [
                    {
                        "uuid": node_map[uid]["uuid"],
                        "name": node_map[uid]["name"],
                        "labels": node_map[uid]["labels"],
                        "summary": node_map[uid].get("summary", ""),
                    }
                    for uid in related_node_uuids
                    if uid in node_map
                ]

            filtered_entities.append(entity)

        logger.info(
            f"Filtering complete: total={total_count}, matched={len(filtered_entities)}, "
            f"types={entity_types_found}"
        )
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str,
    ) -> Optional[EntityNode]:
        try:
            raw = self._call_with_retry(
                func=lambda: get_node_by_uuid(self._driver, entity_uuid),
                operation_name=f"get node (uuid={entity_uuid[:8]}...)",
            )
            if not raw:
                return None
            edges = self.get_node_edges(entity_uuid)
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            related_edges = []
            related_node_uuids: Set[str] = set()
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            return EntityNode(
                uuid=raw.get("uuid", ""),
                name=raw.get("name", ""),
                labels=raw.get("labels_list", []),
                summary=raw.get("summary", ""),
                attributes=raw.get("attributes", {}),
                related_edges=related_edges,
                related_nodes=[
                    {
                        "uuid": node_map[uid]["uuid"],
                        "name": node_map[uid]["name"],
                        "labels": node_map[uid]["labels"],
                        "summary": node_map[uid].get("summary", ""),
                    }
                    for uid in related_node_uuids
                    if uid in node_map
                ],
            )
        except Exception as e:
            logger.error(f"Failed to get entity {entity_uuid}: {e}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_graphiti_entity_reader.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/zep_entity_reader.py backend/tests/test_graphiti_entity_reader.py
git commit -m "feat: migrate zep_entity_reader to Graphiti"
```

---

## Task 5: Migrate zep_graph_memory_updater.py

**Files:**
- Modify: `backend/app/services/zep_graph_memory_updater.py` (rewrite internals, keep all exports)

Exported names that must stay: `ZepGraphMemoryUpdater`, `ZepGraphMemoryManager`, `AgentActivity`.

The `AgentActivity` dataclass and all `to_episode_text()` / `_describe_*` methods are unchanged — they're pure data transformation, no Zep involved.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_graphiti_entity_reader.py` (or create a new test file):

Create `backend/tests/test_graphiti_memory_updater.py`:

```python
"""Unit tests for ZepGraphMemoryUpdater (Graphiti-backed)."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime


class TestAgentActivity:
    def test_to_episode_text_create_post(self):
        from backend.app.services.zep_graph_memory_updater import AgentActivity
        activity = AgentActivity(
            platform="twitter",
            agent_id=1,
            agent_name="Alice",
            action_type="CREATE_POST",
            action_args={"content": "Hello world"},
            round_num=1,
            timestamp=datetime.now().isoformat(),
        )
        text = activity.to_episode_text()
        assert "Alice" in text
        assert "Hello world" in text

    def test_add_activity_skips_do_nothing(self):
        from backend.app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater, AgentActivity
        with patch("backend.app.services.zep_graph_memory_updater.GraphitiClientFactory"):
            updater = ZepGraphMemoryUpdater.__new__(ZepGraphMemoryUpdater)
            updater._skipped_count = 0
            updater._activity_queue = MagicMock()

            activity = AgentActivity(
                platform="twitter", agent_id=1, agent_name="Bob",
                action_type="DO_NOTHING", action_args={}, round_num=1,
                timestamp=datetime.now().isoformat(),
            )
            updater.add_activity(activity)

        updater._activity_queue.put.assert_not_called()
        assert updater._skipped_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_graphiti_memory_updater.py -v
```

Expected: failure because `GraphitiClientFactory` import doesn't exist in the updater yet.

- [ ] **Step 3: Rewrite zep_graph_memory_updater.py**

Replace the entire file content. Keep all `AgentActivity` methods unchanged. Replace only the `ZepGraphMemoryUpdater` and `ZepGraphMemoryManager` internals:

```python
"""
Graphiti graph memory update service.
Dynamically updates agent activities from simulations into the Graphiti graph.

Drop-in replacement for the former Zep-based implementation.
Exports: ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity (unchanged)
"""

import asyncio
import threading
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Queue, Empty

from graphiti_core.nodes import EpisodeType

from ..config import Config
from ..utils.logger import get_logger
from .graphiti_client import GraphitiClientFactory

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent activity record. Unchanged from original."""
    platform: str
    agent_id: int
    agent_name: str
    action_type: str
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        return f"{self.agent_name}: {describe_func()}"

    def _describe_create_post(self):
        content = self.action_args.get("content", "")
        return f"posted: '{content}'" if content else "posted"

    def _describe_like_post(self):
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if post_content and post_author:
            return f"liked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"liked a post: '{post_content}'"
        elif post_author:
            return f"liked a post by {post_author}"
        return "liked a post"

    def _describe_dislike_post(self):
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if post_content and post_author:
            return f"disliked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"disliked a post: '{post_content}'"
        elif post_author:
            return f"disliked a post by {post_author}"
        return "disliked a post"

    def _describe_repost(self):
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        if original_content and original_author:
            return f"reposted {original_author}'s post: '{original_content}'"
        elif original_content:
            return f"reposted a post: '{original_content}'"
        elif original_author:
            return f"reposted a post by {original_author}"
        return "reposted a post"

    def _describe_quote_post(self):
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        if original_content and original_author:
            base = f"quoted {original_author}'s post '{original_content}'"
        elif original_content:
            base = f"quoted a post '{original_content}'"
        elif original_author:
            base = f"quoted a post by {original_author}"
        else:
            base = "quoted a post"
        return f"{base}, with comment: '{quote_content}'" if quote_content else base

    def _describe_follow(self):
        target = self.action_args.get("target_user_name", "")
        return f"followed user '{target}'" if target else "followed a user"

    def _describe_create_comment(self):
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if content:
            if post_content and post_author:
                return f"commented on {post_author}'s post '{post_content}': '{content}'"
            elif post_content:
                return f"commented on post '{post_content}': '{content}'"
            elif post_author:
                return f"commented on a post by {post_author}: '{content}'"
            return f"commented: '{content}'"
        return "created a comment"

    def _describe_like_comment(self):
        cc = self.action_args.get("comment_content", "")
        ca = self.action_args.get("comment_author_name", "")
        if cc and ca:
            return f"liked {ca}'s comment: '{cc}'"
        elif cc:
            return f"liked a comment: '{cc}'"
        elif ca:
            return f"liked a comment by {ca}"
        return "liked a comment"

    def _describe_dislike_comment(self):
        cc = self.action_args.get("comment_content", "")
        ca = self.action_args.get("comment_author_name", "")
        if cc and ca:
            return f"disliked {ca}'s comment: '{cc}'"
        elif cc:
            return f"disliked a comment: '{cc}'"
        elif ca:
            return f"disliked a comment by {ca}"
        return "disliked a comment"

    def _describe_search(self):
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"searched for '{query}'" if query else "performed a search"

    def _describe_search_user(self):
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"searched for user '{query}'" if query else "searched for users"

    def _describe_mute(self):
        target = self.action_args.get("target_user_name", "")
        return f"muted user '{target}'" if target else "muted a user"

    def _describe_generic(self):
        return f"performed action: {self.action_type}"


class ZepGraphMemoryUpdater:
    """
    Graphiti-backed graph memory updater.
    Interface identical to the former ZepGraphMemoryUpdater.
    """

    BATCH_SIZE = 5
    PLATFORM_DISPLAY_NAMES = {'twitter': 'World 1', 'reddit': 'World 2'}
    SEND_INTERVAL = 0.5
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; unused.
        self.graph_id = graph_id
        self._graphiti = GraphitiClientFactory.get_client()
        self._activity_queue: Queue = Queue()
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [], 'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._total_activities = 0
        self._total_sent = 0
        self._total_items_sent = 0
        self._failed_count = 0
        self._skipped_count = 0
        logger.info(f"ZepGraphMemoryUpdater initialized: graph_id={graph_id}")

    def _get_platform_display_name(self, platform: str) -> str:
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"GraphitiMemoryUpdater-{self.graph_id[:8]}",
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater started: graph_id={self.graph_id}")

    def stop(self):
        self._running = False
        self._flush_remaining()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        logger.info(
            f"ZepGraphMemoryUpdater stopped: graph_id={self.graph_id}, "
            f"total_activities={self._total_activities}, "
            f"batches_sent={self._total_sent}, "
            f"items_sent={self._total_items_sent}, "
            f"failed={self._failed_count}, "
            f"skipped={self._skipped_count}"
        )

    def add_activity(self, activity: AgentActivity):
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Queued activity: {activity.agent_name} - {activity.action_type}")

    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        if "event_type" in data:
            return
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        self.add_activity(activity)

    def _worker_loop(self):
        import time
        while self._running or not self._activity_queue.empty():
            try:
                try:
                    activity = self._activity_queue.get(timeout=1)
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            self._send_batch_activities(batch, platform)
                            time.sleep(self.SEND_INTERVAL)
                except Empty:
                    pass
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
                import time as t
                t.sleep(1)

    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        import time
        if not activities:
            return
        combined_text = "\n".join(a.to_episode_text() for a in activities)
        ts = int(datetime.now().timestamp())
        display_name = self._get_platform_display_name(platform)

        async def _add():
            await self._graphiti.add_episode(
                name=f"{platform}_batch_{ts}",
                episode_body=combined_text,
                source_description=f"simulation activity log ({display_name})",
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.text,
                group_id=self.graph_id,
            )

        for attempt in range(self.MAX_RETRIES):
            try:
                asyncio.run(_add())
                self._total_sent += 1
                self._total_items_sent += len(activities)
                logger.info(
                    f"Sent {len(activities)} {display_name} activities to group {self.graph_id}"
                )
                return
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Batch send failed (attempt {attempt+1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Batch send failed after {self.MAX_RETRIES} retries: {e}")
                    self._failed_count += 1

    def _flush_remaining(self):
        from queue import Empty as QEmpty
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except QEmpty:
                break
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    logger.info(f"Flushing {len(buffer)} activities for {self._get_platform_display_name(platform)}")
                    self._send_batch_activities(buffer, platform)
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []

    def get_stats(self) -> Dict[str, Any]:
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,
            "batches_sent": self._total_sent,
            "items_sent": self._total_items_sent,
            "failed_count": self._failed_count,
            "skipped_count": self._skipped_count,
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """Manages multiple ZepGraphMemoryUpdater instances. Interface unchanged."""

    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    _stop_all_done = False

    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            logger.info(f"Created updater: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater

    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id: str):
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Stopped updater: simulation_id={simulation_id}")

    @classmethod
    def stop_all(cls):
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        with cls._lock:
            for simulation_id, updater in list(cls._updaters.items()):
                try:
                    updater.stop()
                except Exception as e:
                    logger.error(f"Failed to stop updater {simulation_id}: {e}")
            cls._updaters.clear()
            logger.info("Stopped all graph memory updaters")

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        return {sim_id: u.get_stats() for sim_id, u in cls._updaters.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_graphiti_memory_updater.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/zep_graph_memory_updater.py backend/tests/test_graphiti_memory_updater.py
git commit -m "feat: migrate zep_graph_memory_updater to Graphiti"
```

---

## Task 6: Migrate zep_tools.py

**Files:**
- Modify: `backend/app/services/zep_tools.py` (rewrite internals, keep all exports)

Exported names that must stay: `ZepToolsService`, `SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult`.

All dataclasses (`SearchResult`, `NodeInfo`, `EdgeInfo`, `InsightForgeResult`) remain unchanged — copy them verbatim from the original file. Only `ZepToolsService.__init__` and methods that call Zep SDK are replaced.

- [ ] **Step 1: Read the rest of zep_tools.py before starting**

Read lines 715–end of the original file to see all `ZepToolsService` methods before rewriting:

```bash
cd backend && grep -n "def " app/services/zep_tools.py
```

Note all method names. Methods that call Zep SDK: `search_graph`, `_local_search`, `get_all_nodes`, `get_all_edges`, `get_node_detail`, `get_node_edges`, and the InsightForge/PanoramaSearch/QuickSearch composite tools.

- [ ] **Step 2: Rewrite ZepToolsService.__init__ and Zep-calling methods**

In the rewritten file, keep all dataclasses unchanged. Replace only the `ZepToolsService` class:

The key replacements in `ZepToolsService`:

```python
# Old __init__:
def __init__(self, api_key=None, llm_client=None):
    self.api_key = api_key or Config.ZEP_API_KEY
    if not self.api_key:
        raise ValueError("ZEP_API_KEY is not configured")
    self.client = Zep(api_key=self.api_key)
    self._llm_client = llm_client

# New __init__:
def __init__(self, api_key=None, llm_client=None):
    # api_key kept for interface compatibility; unused.
    self._graphiti = GraphitiClientFactory.get_client()
    self._llm_client = llm_client
    logger.info("ZepToolsService initialized")
```

Replace `search_graph` and `_local_search`:

```python
def search_graph(self, graph_id: str, query: str, limit: int = 10,
                 scope: str = "edges") -> SearchResult:
    """Semantic search via Graphiti. Falls back to local keyword search on error."""
    logger.info(f"Graph search: graph_id={graph_id}, query={query[:50]}...")
    try:
        return self._call_with_retry(
            func=lambda: self._graphiti_search(graph_id, query, limit, scope),
            operation_name=f"graph search (graph={graph_id})",
        )
    except Exception as e:
        logger.warning(f"Graphiti search failed, falling back to local search: {e}")
        return self._local_search(graph_id, query, limit, scope)

def _graphiti_search(self, graph_id: str, query: str, limit: int, scope: str) -> SearchResult:
    """Execute semantic search via Graphiti async API."""
    async def _search():
        facts, edges, nodes = [], [], []
        if scope in ("edges", "both"):
            edge_results = await self._graphiti.search_(
                query=query, group_ids=[graph_id], num_results=limit
            )
            for edge in (edge_results or []):
                fact = getattr(edge, 'fact', '') or ''
                if fact:
                    facts.append(fact)
                edges.append({
                    "uuid": getattr(edge, 'uuid', ''),
                    "name": getattr(edge, 'name', ''),
                    "fact": fact,
                    "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                    "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                })
        if scope in ("nodes", "both"):
            node_results = await self._graphiti.get_nodes_by_query(
                query=query, group_ids=[graph_id], num_results=limit
            )
            for node in (node_results or []):
                summary = getattr(node, 'summary', '') or ''
                name = getattr(node, 'name', '') or ''
                nodes.append({
                    "uuid": getattr(node, 'uuid', ''),
                    "name": name,
                    "labels": getattr(node, 'labels', []),
                    "summary": summary,
                })
                if summary:
                    facts.append(f"[{name}]: {summary}")
        return facts, edges, nodes

    facts, edges, nodes = asyncio.run(_search())
    return SearchResult(facts=facts, edges=edges, nodes=nodes, query=query,
                        total_count=len(facts))
```

Replace `get_all_nodes` and `get_all_edges`:

```python
def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
    logger.info(f"Fetching all nodes for graph {graph_id}...")
    raw = fetch_all_nodes(self._graphiti.driver, graph_id)
    result = [
        NodeInfo(
            uuid=r.get("uuid", ""),
            name=r.get("name", ""),
            labels=r.get("labels_list", []),
            summary=r.get("summary", ""),
            attributes={},
        )
        for r in raw
    ]
    logger.info(f"Fetched {len(result)} nodes")
    return result

def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
    logger.info(f"Fetching all edges for graph {graph_id}...")
    raw = fetch_all_edges(self._graphiti.driver, graph_id)
    result = []
    for r in raw:
        ei = EdgeInfo(
            uuid=r.get("uuid", ""),
            name=r.get("name", ""),
            fact=r.get("fact", ""),
            source_node_uuid=r.get("source_node_uuid", ""),
            target_node_uuid=r.get("target_node_uuid", ""),
        )
        if include_temporal:
            ei.created_at = r.get("created_at")
            ei.valid_at = r.get("valid_at")
            ei.invalid_at = r.get("invalid_at")
            ei.expired_at = r.get("expired_at")
        result.append(ei)
    logger.info(f"Fetched {len(result)} edges")
    return result
```

Replace `get_node_detail` and `get_node_edges`:

```python
def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
    try:
        raw = self._call_with_retry(
            func=lambda: get_node_by_uuid(self._graphiti.driver, node_uuid),
            operation_name=f"get node detail (uuid={node_uuid[:8]}...)",
        )
        if not raw:
            return None
        return NodeInfo(
            uuid=raw.get("uuid", ""),
            name=raw.get("name", ""),
            labels=raw.get("labels_list", []),
            summary=raw.get("summary", ""),
            attributes={},
        )
    except Exception as e:
        logger.error(f"get_node_detail failed: {e}")
        return None

def get_node_edges(self, node_uuid: str, graph_id: str) -> List[EdgeInfo]:
    try:
        raw = self._call_with_retry(
            func=lambda: get_edges_for_node(self._graphiti.driver, node_uuid),
            operation_name=f"get node edges (node={node_uuid[:8]}...)",
        )
        return [
            EdgeInfo(
                uuid=r.get("uuid", ""),
                name=r.get("name", ""),
                fact=r.get("fact", ""),
                source_node_uuid=r.get("source_node_uuid", ""),
                target_node_uuid=r.get("target_node_uuid", ""),
            )
            for r in raw
        ]
    except Exception as e:
        logger.warning(f"get_node_edges failed: {e}")
        return []
```

Also add these imports at the top of the rewritten file:

```python
import asyncio
from .graphiti_client import GraphitiClientFactory
from ..utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, get_node_by_uuid, get_edges_for_node
```

Remove the old Zep imports:
```python
# Remove these:
from zep_cloud.client import Zep
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
```

- [ ] **Step 3: Verify no import errors**

```bash
cd backend && uv run python -c "from app.services.zep_tools import ZepToolsService; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/zep_tools.py
git commit -m "feat: migrate zep_tools to Graphiti"
```

---

## Task 7: Migrate graph_builder.py

**Files:**
- Modify: `backend/app/services/graph_builder.py` (full rewrite)

- [ ] **Step 1: Rewrite graph_builder.py**

```python
"""
Graph building service.
Builds a standalone knowledge graph from text using Graphiti.

Drop-in replacement for the former Zep-based GraphBuilderService.
"""

import uuid
import time
import threading
import asyncio
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from graphiti_core.nodes import EpisodeType

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from ..utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, delete_group
from .graphiti_client import GraphitiClientFactory
from .text_processor import TextProcessor

logger = get_logger('mirofish.graph_builder')


@dataclass
class GraphInfo:
    """Graph information."""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graphiti-backed graph building service.
    Interface identical to the former Zep-based implementation.
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; unused.
        self._graphiti = GraphitiClientFactory.get_client()
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size),
        )
        thread.daemon = True
        thread.start()
        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
    ):
        try:
            self.task_manager.update_task(task_id, status=TaskStatus.PROCESSING,
                                          progress=5, message="Starting graph build...")
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(task_id, progress=10,
                                          message=f"Graph ID assigned: {graph_id}")

            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(task_id, progress=15, message="Ontology noted (auto-extraction)")

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(task_id, progress=20,
                                          message=f"Text split into {total_chunks} chunks")

            self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id, progress=20 + int(prog * 0.6), message=msg
                ),
            )

            self.task_manager.update_task(task_id, progress=85,
                                          message="Fetching graph statistics...")
            graph_info = self._get_graph_info(graph_id)

            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            self.task_manager.fail_task(task_id, f"{e}\n{traceback.format_exc()}")

    def create_graph(self, name: str) -> str:
        """
        Generate a group_id for this graph partition.
        Graphiti has no graph-creation API — groups are implicit.
        """
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        logger.info(f"Graph ID assigned: {graph_id} (name='{name}')")
        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        No-op — Graphiti has no ontology API.
        Entity types are extracted automatically by the LLM from ingested text.
        """
        logger.warning(
            "set_ontology() called but Graphiti does not support ontology pre-configuration. "
            "Entity types will be inferred from ingested text."
        )

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        """
        Add text chunks to the graph one by one (Graphiti has no batch-add API).
        Returns an empty list (no episode UUIDs needed for polling).
        """
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            progress = (i + 1) / total_chunks

            if progress_callback:
                progress_callback(
                    f"Processing chunk {i+1}/{total_chunks} (batch {batch_num}/{total_batches})...",
                    progress,
                )

            ts = int(datetime.now().timestamp())
            try:
                asyncio.run(self._graphiti.add_episode(
                    name=f"doc_chunk_{i:04d}_{ts}",
                    episode_body=chunk,
                    source_description="uploaded document",
                    reference_time=datetime.now(timezone.utc),
                    source=EpisodeType.text,
                    group_id=graph_id,
                ))
            except Exception as e:
                logger.error(f"Failed to add chunk {i}: {e}")
                if progress_callback:
                    progress_callback(f"Chunk {i+1} failed: {e}", progress)
                raise

            # Brief delay between episodes to avoid overwhelming the LLM.
            time.sleep(0.5)

        return []  # No episode UUIDs to return

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600,
    ):
        """
        No-op — Graphiti's add_episode processes synchronously before returning.
        """
        if progress_callback:
            progress_callback("Processing complete (Graphiti processes episodes synchronously)", 1.0)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = fetch_all_nodes(self._graphiti.driver, graph_id)
        edges = fetch_all_edges(self._graphiti.driver, graph_id)
        entity_types = set()
        for node in nodes:
            for label in node.get("labels_list", []):
                if label not in {"EntityNode", "Entity", "Node"}:
                    entity_types.add(label)
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes_raw = fetch_all_nodes(self._graphiti.driver, graph_id)
        edges_raw = fetch_all_edges(self._graphiti.driver, graph_id)
        node_map = {n["uuid"]: n.get("name", "") for n in nodes_raw}

        nodes_data = [
            {
                "uuid": n.get("uuid", ""),
                "name": n.get("name", ""),
                "labels": n.get("labels_list", []),
                "summary": n.get("summary", ""),
                "attributes": {},
                "created_at": str(n["created_at"]) if n.get("created_at") else None,
            }
            for n in nodes_raw
        ]

        edges_data = [
            {
                "uuid": e.get("uuid", ""),
                "name": e.get("name", ""),
                "fact": e.get("fact", ""),
                "fact_type": e.get("name", ""),
                "source_node_uuid": e.get("source_node_uuid", ""),
                "target_node_uuid": e.get("target_node_uuid", ""),
                "source_node_name": node_map.get(e.get("source_node_uuid", ""), ""),
                "target_node_name": node_map.get(e.get("target_node_uuid", ""), ""),
                "attributes": {},
                "created_at": str(e["created_at"]) if e.get("created_at") else None,
                "valid_at": str(e["valid_at"]) if e.get("valid_at") else None,
                "invalid_at": str(e["invalid_at"]) if e.get("invalid_at") else None,
                "expired_at": str(e["expired_at"]) if e.get("expired_at") else None,
                "episodes": [],  # Graphiti edges have no episode backlink
            }
            for e in edges_raw
        ]

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Delete all nodes and edges for this graph partition."""
        delete_group(self._graphiti.driver, graph_id)
        logger.info(f"Deleted graph partition: {graph_id}")
```

- [ ] **Step 2: Verify no import errors**

```bash
cd backend && uv run python -c "from app.services.graph_builder import GraphBuilderService; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/graph_builder.py
git commit -m "feat: migrate graph_builder to Graphiti"
```

---

## Task 8: Update oasis_profile_generator.py

**Files:**
- Modify: `backend/app/services/oasis_profile_generator.py` (targeted update only)

Only the `_search_zep_for_entity` method needs changing. All other methods stay.

- [ ] **Step 1: Remove the direct Zep client initialization**

Find and remove from `__init__`:

```python
# Remove these lines from __init__:
self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
self.zep_client = None
self.graph_id = graph_id

if self.zep_api_key:
    try:
        self.zep_client = Zep(api_key=self.zep_api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize Zep client: {e}")
```

Replace with:

```python
# Add to __init__ (keep graph_id parameter):
self.graph_id = graph_id
self._graphiti = GraphitiClientFactory.get_client() if graph_id else None
```

- [ ] **Step 2: Replace _search_zep_for_entity**

The method signature, return type, and all error handling stay the same. Only the two inner functions `search_edges` and `search_nodes` change:

```python
# Replace search_edges() inner function body:
def search_edges():
    async def _search():
        return await self._graphiti.search_(
            query=comprehensive_query,
            group_ids=[self.graph_id],
            num_results=30,
        )
    max_retries = 3
    delay = 2.0
    for attempt in range(max_retries):
        try:
            return asyncio.run(_search())
        except Exception as e:
            if attempt < max_retries - 1:
                import time
                logger.debug(f"Edge search attempt {attempt+1} failed: {str(e)[:80]}, retrying...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.debug(f"Edge search failed after {max_retries} attempts: {e}")
    return None

# Replace search_nodes() inner function body:
def search_nodes():
    async def _search():
        return await self._graphiti.get_nodes_by_query(
            query=comprehensive_query,
            group_ids=[self.graph_id],
            num_results=20,
        )
    max_retries = 3
    delay = 2.0
    for attempt in range(max_retries):
        try:
            return asyncio.run(_search())
        except Exception as e:
            if attempt < max_retries - 1:
                import time
                logger.debug(f"Node search attempt {attempt+1} failed: {str(e)[:80]}, retrying...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.debug(f"Node search failed after {max_retries} attempts: {e}")
    return None
```

Also update the result-parsing section — Graphiti returns `EntityEdge` and `EntityNode` objects (not Zep's response objects):

```python
# Replace edge result parsing:
# Old: if hasattr(edge_result, 'edges') and edge_result.edges:
#          for edge in edge_result.edges:
# New (edge_result is now a list of EntityEdge):
all_facts = set()
if edge_result:
    for edge in edge_result:
        fact = getattr(edge, 'fact', '') or ''
        if fact:
            all_facts.add(fact)
results["facts"] = list(all_facts)

# Replace node result parsing:
# Old: if hasattr(node_result, 'nodes') and node_result.nodes:
#          for node in node_result.nodes:
# New (node_result is now a list of EntityNode):
all_summaries = set()
if node_result:
    for node in node_result:
        summary = getattr(node, 'summary', '') or ''
        name = getattr(node, 'name', '') or ''
        if summary:
            all_summaries.add(summary)
        if name and name != entity_name:
            all_summaries.add(f"Related entity: {name}")
results["node_summaries"] = list(all_summaries)
```

- [ ] **Step 3: Update imports at top of file**

Remove:

```python
from zep_cloud.client import Zep
```

Add:

```python
import asyncio
from .graphiti_client import GraphitiClientFactory
```

Also remove the `zep_api_key` parameter from `__init__` signature (or keep it as a no-op for backward compat — callers may pass it). Check callers:

```bash
grep -rn "OasisProfileGenerator(" backend/
```

If any callers pass `zep_api_key=...`, keep the parameter in the signature but ignore it.

- [ ] **Step 4: Verify no import errors**

```bash
cd backend && uv run python -c "from app.services.oasis_profile_generator import OasisProfileGenerator; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/oasis_profile_generator.py
git commit -m "feat: migrate oasis_profile_generator to Graphiti"
```

---

## Task 9: Cleanup

**Files:**
- Delete: `backend/app/utils/zep_paging.py`

- [ ] **Step 1: Verify no remaining imports of zep_paging**

```bash
grep -rn "zep_paging\|from zep_cloud\|import Zep" backend/app/
```

Expected: zero results (all callers have been migrated).

- [ ] **Step 2: Verify no remaining imports of zep_cloud**

```bash
grep -rn "zep_cloud\|ZEP_API_KEY" backend/app/
```

Expected: zero results.

- [ ] **Step 3: Delete zep_paging.py**

```bash
rm backend/app/utils/zep_paging.py
```

- [ ] **Step 4: Run all existing tests**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all existing tests pass, no import errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete zep_paging.py, complete Graphiti migration"
```

---

## Task 10: Integration Smoke Test

No automated tests — manual verification against live Neo4j + LM Studio.

**Prerequisites:** Neo4j running, LM Studio serving `mlx-community/Qwen3-Embedding-4B-mxfp8` on port 1234, `.env.local` populated with Neo4j credentials.

- [ ] **Step 1: Start the Flask backend**

```bash
cd backend && uv run flask run
```

Expected: starts without errors. Log should show `Graphiti client initialized, Neo4j indexes verified`.

- [ ] **Step 2: Test episode ingestion**

```bash
cd backend && uv run python -c "
import asyncio
from datetime import datetime, timezone
from graphiti_core.nodes import EpisodeType
from app.services.graphiti_client import GraphitiClientFactory

g = GraphitiClientFactory.get_client()
asyncio.run(g.add_episode(
    name='smoke_test_001',
    episode_body='Alice Chen is a software engineer at MiroFish. She specializes in graph databases.',
    source_description='smoke test',
    reference_time=datetime.now(timezone.utc),
    source=EpisodeType.text,
    group_id='smoke_test_group',
))
print('Episode ingested successfully')
"
```

Expected: `Episode ingested successfully`. Open Neo4j Browser and verify nodes appear with group_id `smoke_test_group`.

- [ ] **Step 3: Test search retrieval**

```bash
cd backend && uv run python -c "
import asyncio
from app.services.graphiti_client import GraphitiClientFactory

g = GraphitiClientFactory.get_client()
results = asyncio.run(g.search_('Alice Chen graph databases', group_ids=['smoke_test_group'], num_results=5))
print(f'Search returned {len(results)} edges')
for r in results:
    print(' -', getattr(r, 'fact', ''))
"
```

Expected: 1 or more edges with facts about Alice.

- [ ] **Step 4: Test ZepEntityReader against real data**

```bash
cd backend && uv run python -c "
from app.services.zep_entity_reader import ZepEntityReader
reader = ZepEntityReader()
entities = reader.filter_defined_entities('smoke_test_group')
print(f'Found {entities.total_count} total nodes, {entities.filtered_count} typed entities')
print('Entity types:', entities.entity_types)
"
```

Expected: total_count > 0. If filtered_count is 0, the entity type labels may be stored differently — revisit Task 3 schema verification and update `_DEFAULT_LABELS` set.

- [ ] **Step 5: Test ZepToolsService search**

```bash
cd backend && uv run python -c "
from app.services.zep_tools import ZepToolsService
tools = ZepToolsService()
result = tools.search_graph('smoke_test_group', 'Alice Chen', limit=5)
print('Facts:', result.facts[:3])
"
```

Expected: 1+ facts returned.

- [ ] **Step 6: Test GraphBuilderService**

Via the Flask API or directly:

```bash
cd backend && uv run python -c "
from app.services.graph_builder import GraphBuilderService
svc = GraphBuilderService()
gid = svc.create_graph('Test Graph')
print('Graph ID:', gid)
svc.add_text_batches(gid, ['Test chunk one.', 'Test chunk two.'], batch_size=2)
info = svc._get_graph_info(gid)
print('Graph info:', info.to_dict())
svc.delete_graph(gid)
print('Graph deleted')
"
```

Expected: graph ID assigned, chunks ingested, node/edge counts returned, graph deleted.

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "chore: Graphiti migration complete — smoke tests verified"
```
