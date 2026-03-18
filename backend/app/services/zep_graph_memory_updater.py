"""
Graphiti graph memory update service.
Dynamically updates agent activities from simulations into the Graphiti graph.

Drop-in replacement for the former Zep-based implementation.
Exports: ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity (unchanged)
"""

import asyncio
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Queue, Empty

from graphiti_core.nodes import EpisodeType

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
                    batch_to_send = None
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch_to_send = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                    if batch_to_send:
                        self._send_batch_activities(batch_to_send, platform)
                        time.sleep(self.SEND_INTERVAL)
                except Empty:
                    pass
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
                time.sleep(1)

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
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        batches_to_send = {}
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    batches_to_send[platform] = list(buffer)
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []

        for platform, batch in batches_to_send.items():
            logger.info(f"Flushing {len(batch)} activities for {self._get_platform_display_name(platform)}")
            self._send_batch_activities(batch, platform)

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
