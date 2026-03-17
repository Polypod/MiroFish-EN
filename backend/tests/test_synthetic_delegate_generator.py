"""Tests for SyntheticDelegateGenerator dataclasses and helpers."""
import pytest
from backend.app.services.synthetic_delegate_generator import (
    SyntheticEntityNode,
    CompanySpec,
    DelegateDistribution,
)
from backend.app.services.synthetic_delegate_generator import SyntheticDelegateGenerator


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


class TestCompanyLibrary:
    def test_load_company_library_returns_25_companies(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        lib = gen._load_company_library()
        assert len(lib["companies"]) == 25

    def test_load_company_library_has_working_groups(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        lib = gen._load_company_library()
        assert "RAN1" in lib["working_groups"]
        assert "SA2" in lib["working_groups"]


class TestBuildDistributionFromManual:
    def test_manual_config_builds_distribution(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        manual = {
            "companies": [
                {"name": "Ericsson", "short_name": "ERX", "region": "EU",
                 "country": "Sweden", "delegate_count": 5, "typical_wgs": ["RAN1"],
                 "typical_stance": "standards-driven"}
            ]
        }
        dist = gen._build_distribution_from_manual(manual, 5, "NR positioning test")
        assert dist.total_delegates == 5
        assert len(dist.companies) == 1
        assert dist.working_groups == ["RAN1"]
        assert dist.topic_context == "NR positioning test"

    def test_manual_config_raises_on_missing_name(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        with pytest.raises(ValueError, match="missing required field"):
            gen._build_distribution_from_manual(
                {"companies": [{"short_name": "ERX", "delegate_count": 5,
                                "typical_wgs": ["RAN1"]}]},
                5, "test"
            )

    def test_manual_config_raises_on_zero_delegate_count(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        with pytest.raises(ValueError, match="delegate_count must be positive"):
            gen._build_distribution_from_manual(
                {"companies": [{"name": "Ericsson", "short_name": "ERX",
                                "region": "EU", "country": "Sweden",
                                "delegate_count": 0, "typical_wgs": ["RAN1"],
                                "typical_stance": "x"}]},
                0, "test"
            )

    def test_manual_config_rescales_when_sum_differs(self):
        """If sum(delegate_count) != total_delegates, values are rescaled."""
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        manual = {
            "companies": [
                {"name": "Ericsson", "short_name": "ERX", "region": "EU",
                 "country": "Sweden", "delegate_count": 10, "typical_wgs": ["RAN1"],
                 "typical_stance": "x"},
                {"name": "Nokia", "short_name": "NOK", "region": "EU",
                 "country": "Finland", "delegate_count": 10, "typical_wgs": ["RAN2"],
                 "typical_stance": "y"},
            ]
        }
        dist = gen._build_distribution_from_manual(manual, 30, "test")
        assert sum(c.delegate_count for c in dist.companies) == 30


class TestBuildDistributionFromPresets:
    def test_preset_distribution_sums_to_total(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        dist = gen._build_distribution_from_presets(30, "test topic")
        assert sum(c.delegate_count for c in dist.companies) == 30

    def test_very_small_total_uses_top_n_companies(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        dist = gen._build_distribution_from_presets(3, "test topic")
        assert len(dist.companies) == 3
        assert all(c.delegate_count == 1 for c in dist.companies)

    def test_all_delegate_counts_positive(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        dist = gen._build_distribution_from_presets(30, "test")
        assert all(c.delegate_count >= 1 for c in dist.companies)
