"""
Graphiti client factory.
Thread-safe singleton — creates the Graphiti client once and caches it.

All async Graphiti calls must go through `run_async()` so they execute on the
single shared event loop that the Graphiti client (and its Neo4j driver) was
created on.  Mixing `asyncio.run()` across threads creates different event
loops, which causes "Future attached to a different loop" errors.
"""

import asyncio
import concurrent.futures
import threading

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_client import OpenAIClient, LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.graphiti_client')

# ---------------------------------------------------------------------------
# Shared persistent event loop
# ---------------------------------------------------------------------------
_event_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Return the shared background event loop, starting it on first call."""
    global _event_loop, _loop_thread
    if _event_loop is not None and _event_loop.is_running():
        return _event_loop
    with _loop_lock:
        if _event_loop is not None and _event_loop.is_running():
            return _event_loop
        _event_loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_event_loop.run_forever, daemon=True)
        _loop_thread.start()
        logger.debug("Graphiti background event loop started")
        return _event_loop


def run_async(coro):
    """
    Run *coro* on the shared Graphiti event loop and block until it completes.
    Safe to call from any thread (including the Flask request thread).
    """
    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------
_client_lock = threading.Lock()


class GraphitiClientFactory:
    """Thread-safe singleton factory for the Graphiti client."""

    _instance: Graphiti | None = None

    @classmethod
    def get_client(cls) -> Graphiti:
        """Return the shared Graphiti client, initializing it on first call."""
        if cls._instance is not None:
            return cls._instance

        with _client_lock:
            if cls._instance is not None:
                return cls._instance

            cls._instance = cls._create_client()
            return cls._instance

    @classmethod
    def _create_client(cls) -> Graphiti:
        """Instantiate and initialize the Graphiti client on the shared loop."""
        if not Config.NEO4J_PASSWORD:
            raise RuntimeError("Graphiti client cannot initialize — NEO4J_PASSWORD is not set")

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

        # Patch create_batch to guard against empty input lists.
        # Graphiti calls create_batch([]) when a chunk produces no entities
        # (e.g. table separators, blank lines).  LM Studio returns an empty
        # response for an empty input which the OpenAI SDK then raises as
        # "No embedding data received".  Short-circuiting here avoids the call.
        _original_create_batch = embedder.create_batch

        async def _safe_create_batch(input_data_list):
            if not input_data_list:
                return []
            return await _original_create_batch(input_data_list)

        embedder.create_batch = _safe_create_batch

        cross_encoder = OpenAIRerankerClient(
            config=LLMConfig(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        )

        # Build the Graphiti instance *inside* the shared loop so the Neo4j
        # async driver is bound to it from the start.
        loop = _get_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            cls._init_graphiti(llm_client, embedder, cross_encoder), loop
        )
        return future.result()

    @staticmethod
    async def _init_graphiti(llm_client, embedder, cross_encoder) -> Graphiti:
        graphiti = Graphiti(
            uri=Config.NEO4J_URI,
            user=Config.NEO4J_USER,
            password=Config.NEO4J_PASSWORD,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )
        try:
            await graphiti.build_indices_and_constraints()
            logger.info("Graphiti client initialized, Neo4j indexes verified")
        except Exception as e:
            logger.warning(f"Could not build Neo4j indexes (may already exist): {e}")
        return graphiti
