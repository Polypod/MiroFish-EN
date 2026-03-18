"""Unit tests for graphiti_cypher utilities."""
import pytest
from unittest.mock import AsyncMock, MagicMock


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
        mock_driver.execute_query = AsyncMock(
            return_value=([mock_record], None, None)
        )

        result = fetch_all_nodes(mock_driver, "test_group")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_paginates_across_multiple_pages(self):
        from backend.app.utils.graphiti_cypher import fetch_all_nodes

        page1 = [{"uuid": f"id{i:03d}", "name": f"Node{i}", "summary": "",
                  "labels_list": ["EntityNode"], "created_at": None} for i in range(5)]
        page2 = [{"uuid": f"id{i:03d}", "name": f"Node{i}", "summary": "",
                  "labels_list": ["EntityNode"], "created_at": None} for i in range(5, 8)]
        mock_driver = MagicMock()
        mock_driver.execute_query = AsyncMock(
            side_effect=[(page1, None, None), (page2, None, None)]
        )

        result = fetch_all_nodes(mock_driver, "test_group", page_size=5)
        assert len(result) == 8
