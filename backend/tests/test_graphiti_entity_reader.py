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
    def test_filter_defined_entities_skips_plain_entity_nodes(self):
        """Nodes with only default labels are excluded."""
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

    def test_entity_node_get_entity_type_returns_none_for_default_only(self):
        """EntityNode.get_entity_type() returns None if only default labels."""
        from backend.app.services.zep_entity_reader import EntityNode
        node = EntityNode(
            uuid="x", name="Generic", labels=["EntityNode"],
            summary="", attributes={}
        )
        assert node.get_entity_type() is None
