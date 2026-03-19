"""
Graph building service.
Builds a standalone knowledge graph from text using Graphiti.

Drop-in replacement for the former Zep-based GraphBuilderService.
"""

import json
import os
import uuid
import time
import threading
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timezone

from graphiti_core.nodes import EpisodeType

from ....utils.logger import get_logger
from ....utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, delete_group
from ....models.task import TaskManager, TaskStatus
from ...graphiti_client import GraphitiClientFactory, run_async
from ...text_processor import TextProcessor

logger = get_logger('mirofish.graph_builder')

# Retry configuration for transient network/API failures
_RETRY_MAX = 5
_RETRY_BASE_DELAY = 2.0   # seconds
_RETRY_MAX_DELAY = 60.0   # seconds


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

    # Checkpoint files live here so progress survives server restarts.
    CHECKPOINT_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../../../../uploads/graph_checkpoints'
    )

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; unused.
        self._graphiti = GraphitiClientFactory.get_client()
        self.task_manager = TaskManager()
        os.makedirs(self.CHECKPOINT_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self, graph_id: str) -> str:
        return os.path.join(self.CHECKPOINT_DIR, f"{graph_id}.json")

    def _save_checkpoint(self, graph_id: str, completed: Set[int], total: int, graph_name: str):
        """Persist which chunks have been ingested so a retry can skip them."""
        data = {
            "graph_id": graph_id,
            "graph_name": graph_name,
            "total_chunks": total,
            "completed_indices": sorted(completed),
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._checkpoint_path(graph_id), 'w') as f:
            json.dump(data, f)

    def _load_checkpoint(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Return checkpoint data or None if no checkpoint exists."""
        path = self._checkpoint_path(graph_id)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def _clear_checkpoint(self, graph_id: str):
        path = self._checkpoint_path(graph_id)
        if os.path.exists(path):
            os.remove(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
        resume_graph_id: Optional[str] = None,
    ) -> str:
        """
        Start an async graph build.

        Pass ``resume_graph_id`` to continue a previously interrupted build:
        the worker will load the saved checkpoint and skip chunks that already
        succeeded, picking up from where the last run stopped.
        """
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
                "resume_graph_id": resume_graph_id,
            },
        )
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, resume_graph_id),
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
        resume_graph_id: Optional[str] = None,
    ):
        graph_id = None
        try:
            self.task_manager.update_task(task_id, status=TaskStatus.PROCESSING,
                                          progress=5, message="Starting graph build...")

            # Reuse existing graph_id when resuming, otherwise mint a new one.
            if resume_graph_id:
                graph_id = resume_graph_id
                self.task_manager.update_task(task_id, progress=8,
                                              message=f"Resuming graph: {graph_id}")
            else:
                graph_id = self.create_graph(graph_name)
                self.task_manager.update_task(task_id, progress=10,
                                              message=f"Graph ID assigned: {graph_id}")

            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(task_id, progress=15, message="Ontology noted (auto-extraction)")

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(task_id, progress=20,
                                          message=f"Text split into {total_chunks} chunks")

            # Load checkpoint — find out which chunks already succeeded.
            checkpoint = self._load_checkpoint(graph_id)
            skip_indices: Set[int] = set(checkpoint["completed_indices"]) if checkpoint else set()
            if skip_indices:
                self.task_manager.update_task(
                    task_id, progress=20,
                    message=f"Resuming: {len(skip_indices)}/{total_chunks} chunks already done"
                )

            self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id, progress=20 + int(prog * 0.6), message=msg
                ),
                skip_indices=skip_indices,
                graph_name=graph_name,
            )

            self.task_manager.update_task(task_id, progress=85,
                                          message="Fetching graph statistics...")
            graph_info = self._get_graph_info(graph_id)

            self._clear_checkpoint(graph_id)
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Graph build failed (task={task_id}, graph={graph_id}): {e}\n{tb}")
            # Surface the graph_id in the failure result so the caller can offer resume.
            self.task_manager.update_task(task_id, result={
                "graph_id": graph_id,
                "resumable": graph_id is not None,
            })
            self.task_manager.fail_task(task_id, f"{e}\n{tb}")

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
        skip_indices: Optional[Set[int]] = None,
        graph_name: str = "MiroFish Graph",
    ) -> List[str]:
        """
        Add text chunks to the graph one by one (Graphiti has no batch-add API).

        Each chunk is retried up to ``_RETRY_MAX`` times with exponential backoff
        before the exception propagates.  Successfully ingested chunk indices are
        written to a checkpoint file after every chunk so a later call with
        ``skip_indices`` (loaded from that file) can resume mid-build.

        Returns an empty list (no episode UUIDs needed for polling).
        """
        total_chunks = len(chunks)
        completed: Set[int] = set(skip_indices or [])

        for i, chunk in enumerate(chunks):
            if i in completed:
                # Already ingested in a previous run — skip silently.
                continue

            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            progress = (i + 1) / total_chunks

            if progress_callback:
                progress_callback(
                    f"Processing chunk {i+1}/{total_chunks} (batch {batch_num}/{total_batches})...",
                    progress,
                )

            ts = int(datetime.now().timestamp())
            last_exc: Optional[Exception] = None

            for attempt in range(_RETRY_MAX + 1):
                try:
                    run_async(self._graphiti.add_episode(
                        name=f"doc_chunk_{i:04d}_{ts}",
                        episode_body=chunk,
                        source_description="uploaded document",
                        reference_time=datetime.now(timezone.utc),
                        source=EpisodeType.text,
                        group_id=graph_id,
                    ))
                    last_exc = None
                    break  # success
                except Exception as e:
                    last_exc = e
                    if attempt < _RETRY_MAX:
                        delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                        logger.warning(
                            f"Chunk {i+1}/{total_chunks} failed (attempt {attempt+1}/{_RETRY_MAX}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        if progress_callback:
                            progress_callback(
                                f"Chunk {i+1} retry {attempt+1}/{_RETRY_MAX} after error: {e}",
                                progress,
                            )
                        time.sleep(delay)

            if last_exc is not None:
                logger.error(f"Chunk {i+1}/{total_chunks} failed after {_RETRY_MAX} retries: {last_exc}")
                if progress_callback:
                    progress_callback(f"Chunk {i+1} permanently failed: {last_exc}", progress)
                # Checkpoint what we have so far before raising.
                self._save_checkpoint(graph_id, completed, total_chunks, graph_name)
                raise last_exc

            # Mark chunk as done and persist progress.
            completed.add(i)
            self._save_checkpoint(graph_id, completed, total_chunks, graph_name)

            time.sleep(0.5)

        return []

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
                if label not in {"Entity", "Node"}:
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
                "episodes": [],
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
