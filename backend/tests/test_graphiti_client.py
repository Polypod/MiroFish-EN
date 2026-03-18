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
