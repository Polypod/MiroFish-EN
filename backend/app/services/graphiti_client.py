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
