"""Unit tests for ZepGraphMemoryUpdater (Graphiti-backed)."""
import pytest
from unittest.mock import MagicMock, patch
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
        with patch("backend.app.services._backends.graphiti.memory_updater.GraphitiClientFactory"):
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
