"""Tests for SimulationConfigGenerator delegate entity type support."""
import pytest
from backend.app.services.simulation_config_generator import SimulationConfigGenerator
from backend.app.services.synthetic_delegate_generator import SyntheticEntityNode


class TestDelegateRuleBasedConfig:
    def _make_gen(self):
        gen = SimulationConfigGenerator.__new__(SimulationConfigGenerator)
        return gen

    def test_delegate_entity_type_returns_conference_hours(self):
        gen = self._make_gen()
        node = SyntheticEntityNode(uuid="u1", name="Lena Berg", entity_type="Delegate")
        cfg = gen._generate_agent_config_by_rule(node)
        # Conference hours: 8-17 (not Chinese evening peak)
        assert 8 in cfg["active_hours"]
        assert 17 in cfg["active_hours"]
        assert cfg["activity_level"] == 0.6

    def test_delegate_activity_level_is_0_6(self):
        gen = self._make_gen()
        node = SyntheticEntityNode(uuid="u1", name="Test", entity_type="Delegate")
        cfg = gen._generate_agent_config_by_rule(node)
        assert cfg["activity_level"] == 0.6

    def test_delegate_comments_more_than_posts(self):
        gen = self._make_gen()
        node = SyntheticEntityNode(uuid="u1", name="Test", entity_type="Delegate")
        cfg = gen._generate_agent_config_by_rule(node)
        assert cfg["comments_per_hour"] > cfg["posts_per_hour"]

    def test_type_annotation_accepts_synthetic_node(self):
        """SyntheticEntityNode must work wherever EntityNode is used in generate_config."""
        node = SyntheticEntityNode(uuid="u1", name="Test")
        # get_entity_type() must return a string (not None)
        assert isinstance(node.get_entity_type(), str)
