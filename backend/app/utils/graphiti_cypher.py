"""
Graphiti bulk retrieval utilities.

Fetches all nodes/edges for a group using keyset pagination via Neo4j Cypher.
Replaces zep_paging.py.

IMPORTANT: The node label (:EntityNode) and property names below were verified
against the actual Neo4j schema. If the schema differs, update the MATCH clauses.
"""

import asyncio
from typing import Any, Dict, List, Optional

from .logger import get_logger

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
    # Adjust :EntityNode and n.group_id if your schema uses different names.
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
