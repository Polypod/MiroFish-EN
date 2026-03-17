"""Tests for SyntheticDelegateGenerator dataclasses and helpers."""
import json
import pytest
from unittest.mock import MagicMock, patch
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


class TestInferDistribution:
    def _make_gen(self):
        """Create generator with mocked LLM."""
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        gen._model = "test-model"
        gen._api_key = "test"
        gen._base_url = "http://localhost"
        mock_llm = MagicMock()
        gen._llm = mock_llm
        return gen, mock_llm

    def _make_llm_response(self, content: str):
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    def test_manual_config_skips_llm(self):
        gen, mock_llm = self._make_gen()
        manual = {
            "companies": [
                {"name": "Ericsson", "short_name": "ERX", "region": "EU",
                 "country": "Sweden", "delegate_count": 10, "typical_wgs": ["RAN1"],
                 "typical_stance": "standards-driven"}
            ]
        }
        dist = gen.infer_distribution("doc text", "test req", 10, manual_config=manual)
        mock_llm.chat.completions.create.assert_not_called()
        assert dist.total_delegates == 10

    def test_llm_response_parsed_into_distribution(self):
        gen, mock_llm = self._make_gen()
        llm_json = json.dumps({
            "topic_context": "NR positioning accuracy for Release 18",
            "companies": [
                {"name": "Ericsson", "short_name": "ERX", "region": "EU",
                 "country": "Sweden", "delegate_count": 12, "typical_wgs": ["RAN1"],
                 "typical_stance": "standards-driven"},
                {"name": "Nokia", "short_name": "NOK", "region": "EU",
                 "country": "Finland", "delegate_count": 10, "typical_wgs": ["RAN2"],
                 "typical_stance": "collaborative"},
            ]
        })
        mock_llm.chat.completions.create.return_value = self._make_llm_response(llm_json)
        dist = gen.infer_distribution("some 3gpp document", "NR positioning", 22)
        assert dist.topic_context == "NR positioning accuracy for Release 18"
        assert len(dist.companies) == 2
        assert dist.total_delegates == 22
        assert "RAN1" in dist.working_groups

    def test_llm_failure_falls_back_to_presets(self):
        gen, mock_llm = self._make_gen()
        mock_llm.chat.completions.create.side_effect = Exception("LLM timeout")
        dist = gen.infer_distribution("doc text", "test req", 30)
        # Should not raise — falls back to preset distribution
        assert dist.total_delegates == 30
        assert len(dist.companies) > 0


class TestRuleBasedBatch:
    def _make_gen(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        return gen

    def test_rule_based_batch_returns_correct_count(self):
        gen = self._make_gen()
        company = CompanySpec("Ericsson", "ERX", "EU", "Sweden", 5, ["RAN1"], "x")
        profiles, nodes = gen._generate_rule_based_batch(company, 5, id_offset=0)
        assert len(profiles) == 5
        assert len(nodes) == 5

    def test_rule_based_profile_has_required_fields(self):
        gen = self._make_gen()
        company = CompanySpec("Ericsson", "ERX", "EU", "Sweden", 3, ["RAN1"], "x")
        profiles, nodes = gen._generate_rule_based_batch(company, 3, id_offset=0)
        for p in profiles:
            assert p.user_id >= 0
            assert p.name
            assert p.user_name
            assert p.bio
            assert p.persona
            assert p.company == "Ericsson"
        for n in nodes:
            assert n.company == "Ericsson"
            assert n.get_entity_type() == "Delegate"

    def test_rule_based_usernames_are_unique(self):
        gen = self._make_gen()
        company = CompanySpec("Nokia", "NOK", "EU", "Finland", 10, ["RAN2"], "y")
        profiles, _ = gen._generate_rule_based_batch(company, 10, id_offset=0)
        usernames = [p.user_name for p in profiles]
        assert len(usernames) == len(set(usernames))

    def test_id_offset_applied(self):
        gen = self._make_gen()
        company = CompanySpec("Ericsson", "ERX", "EU", "Sweden", 3, ["RAN1"], "x")
        profiles, _ = gen._generate_rule_based_batch(company, 3, id_offset=10)
        assert profiles[0].user_id == 10
        assert profiles[2].user_id == 12


class TestGenerateMethod:
    def _make_gen_with_mock_llm(self, llm_response: str):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        gen._model = "test-model"
        gen._api_key = "test"
        gen._base_url = "http://localhost"
        mock_llm = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = llm_response
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create.return_value = mock_response
        gen._llm = mock_llm
        return gen

    def _make_distribution(self, delegate_count: int) -> DelegateDistribution:
        return DelegateDistribution(
            companies=[
                CompanySpec("Ericsson", "ERX", "EU", "Sweden",
                            delegate_count, ["RAN1"], "standards-driven")
            ],
            working_groups=["RAN1"],
            topic_context="NR positioning",
            total_delegates=delegate_count,
        )

    def test_generate_returns_correct_counts(self):
        delegate_json = json.dumps([
            {"name": f"Delegate {i}", "username": f"del_{i}_erx",
             "bio": "Engineer at Ericsson", "persona": "You are an Ericsson engineer...",
             "age": 35, "gender": "male", "mbti": "INTJ", "country": "Sweden",
             "company": "Ericsson", "working_group": "RAN1",
             "expertise_areas": ["massive MIMO"], "delegate_role": "delegate",
             "seniority": "senior engineer", "stance": "neutral",
             "karma": 1000, "follower_count": 100}
            for i in range(5)
        ])
        gen = self._make_gen_with_mock_llm(delegate_json)
        dist = self._make_distribution(5)
        nodes, profiles = gen.generate(dist, "doc text", "NR positioning")
        assert len(nodes) == 5
        assert len(profiles) == 5

    def test_generate_falls_back_on_llm_failure(self):
        gen = SyntheticDelegateGenerator.__new__(SyntheticDelegateGenerator)
        gen.company_library = gen._load_company_library()
        gen._model = "test"
        gen._api_key = "test"
        gen._base_url = "http://localhost"
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = Exception("LLM down")
        gen._llm = mock_llm
        dist = self._make_distribution(5)
        nodes, profiles = gen.generate(dist, "doc text", "req")
        assert len(nodes) == 5
        assert len(profiles) == 5

    def test_nodes_have_3gpp_fields(self):
        delegate_json = json.dumps([
            {"name": "Dr. Test", "username": "dr_test_erx",
             "bio": "bio", "persona": "persona...",
             "age": 40, "gender": "female", "mbti": "INTJ", "country": "Sweden",
             "company": "Ericsson", "working_group": "RAN1",
             "expertise_areas": ["MIMO"], "delegate_role": "rapporteur",
             "seniority": "principal", "stance": "pragmatic",
             "karma": 1200, "follower_count": 150}
        ])
        gen = self._make_gen_with_mock_llm(delegate_json)
        dist = self._make_distribution(1)
        nodes, profiles = gen.generate(dist, "doc", "req")
        assert nodes[0].company == "Ericsson"
        assert nodes[0].working_group == "RAN1"
        assert nodes[0].delegate_role == "rapporteur"
