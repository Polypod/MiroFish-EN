"""Tests for SyntheticDelegateGenerator dataclasses and helpers."""
import pytest
from backend.app.services.synthetic_delegate_generator import (
    SyntheticEntityNode,
    CompanySpec,
    DelegateDistribution,
)


class TestSyntheticEntityNode:
    def test_get_entity_type_returns_entity_type(self):
        node = SyntheticEntityNode(uuid="test-uuid", name="Dr. Test")
        assert node.get_entity_type() == "Delegate"

    def test_custom_entity_type(self):
        node = SyntheticEntityNode(uuid="u1", name="Alice", entity_type="Rapporteur")
        assert node.get_entity_type() == "Rapporteur"

    def test_has_required_entity_node_interface(self):
        """SyntheticEntityNode must be duck-typed compatible with EntityNode."""
        node = SyntheticEntityNode(uuid="u1", name="Alice")
        assert hasattr(node, "uuid")
        assert hasattr(node, "name")
        assert hasattr(node, "labels")
        assert hasattr(node, "summary")
        assert hasattr(node, "attributes")
        assert hasattr(node, "related_edges")
        assert hasattr(node, "related_nodes")
        assert isinstance(node.labels, list)
        assert isinstance(node.related_edges, list)
        assert isinstance(node.related_nodes, list)
        assert isinstance(node.attributes, dict)

    def test_3gpp_fields_have_defaults(self):
        node = SyntheticEntityNode(uuid="u1", name="Alice")
        assert node.company == ""
        assert node.working_group == ""
        assert node.delegate_role == "delegate"
        assert node.seniority == "senior engineer"
        assert node.stance == "neutral"


class TestCompanySpec:
    def test_company_spec_fields(self):
        spec = CompanySpec(
            name="Ericsson",
            short_name="ERX",
            region="EU",
            country="Sweden",
            delegate_count=8,
            typical_wgs=["RAN1", "RAN2"],
            typical_stance="standards-driven",
        )
        assert spec.name == "Ericsson"
        assert spec.delegate_count == 8
        assert "RAN1" in spec.typical_wgs


class TestDelegateDistribution:
    def test_distribution_fields(self):
        dist = DelegateDistribution(
            companies=[
                CompanySpec("Ericsson", "ERX", "EU", "Sweden", 8, ["RAN1"], "standards-driven")
            ],
            working_groups=["RAN1"],
            topic_context="NR positioning debate",
            total_delegates=8,
        )
        assert dist.total_delegates == 8
        assert len(dist.companies) == 1
