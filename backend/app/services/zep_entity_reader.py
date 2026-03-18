"""
Graphiti entity read and filter service.
Reads nodes from a Graphiti graph and filters nodes by entity type.

Drop-in replacement for the former Zep-based implementation.
Exports: ZepEntityReader, EntityNode, FilteredEntities (unchanged)
"""

import time
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar
from dataclasses import dataclass, field

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
