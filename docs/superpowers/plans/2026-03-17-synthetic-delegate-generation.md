# Synthetic 3GPP Delegate Generation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate synthetic 3GPP delegate agents (LLM-created fictive persons with company, WG, expertise, role, stance) to supplement or replace real Zep-graph entities in simulations.

**Architecture:** A new `SyntheticDelegateGenerator` service runs inside `prepare_simulation()` after real entity profiles are generated. It makes two LLM calls: one to infer a company/WG distribution from documents, one to batch-generate delegate personas. Results are merged with real profiles before saving and passed to `SimulationConfigGenerator` as duck-typed `SyntheticEntityNode` objects.

**Tech Stack:** Python 3.11, Flask, OpenAI-compatible LLM client, pytest, **Vue 3 + Vite** frontend

**Spec:** `docs/superpowers/specs/2026-03-17-synthetic-delegate-generation-design.md`

---

## Chunk 1: Data Structures and Company Library

### Task 1: Create the 3GPP company library JSON

**Files:**

- Create: `backend/app/data/3gpp_companies.json`

- [ ] **Step 1: Create the data directory and file**

```bash
mkdir -p backend/app/data
```

Create `backend/app/data/3gpp_companies.json`:

```json
{
  "version": "1.0",
  "companies": [
    {
      "name": "Ericsson",
      "short_name": "ERX",
      "region": "EU",
      "country": "Sweden",
      "typical_wgs": ["RAN1", "RAN2", "SA2", "CT1"],
      "typical_stance": "standards-driven, strong on radio access technology",
      "typical_delegate_share": 0.10
    },
    {
      "name": "Nokia",
      "short_name": "NOK",
      "region": "EU",
      "country": "Finland",
      "typical_wgs": ["RAN1", "RAN2", "SA1", "SA2"],
      "typical_stance": "collaborative, broad portfolio across access and core",
      "typical_delegate_share": 0.09
    },
    {
      "name": "Qualcomm",
      "short_name": "QCOM",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["RAN1", "RAN2", "SA2"],
      "typical_stance": "aggressive IPR, strong on physical layer and chipset interests",
      "typical_delegate_share": 0.08
    },
    {
      "name": "Huawei",
      "short_name": "HW",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["RAN1", "RAN2", "RAN3", "SA2"],
      "typical_stance": "prolific contributor, strong on radio and architecture",
      "typical_delegate_share": 0.10
    },
    {
      "name": "Samsung",
      "short_name": "SAM",
      "region": "APAC",
      "country": "South Korea",
      "typical_wgs": ["RAN1", "RAN2", "SA1"],
      "typical_stance": "device-oriented, strong on UE capabilities and features",
      "typical_delegate_share": 0.07
    },
    {
      "name": "ZTE",
      "short_name": "ZTE",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["RAN1", "RAN2", "SA2"],
      "typical_stance": "competitive with Huawei, strong on radio access",
      "typical_delegate_share": 0.06
    },
    {
      "name": "Intel",
      "short_name": "INTL",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["RAN1", "SA2", "CT1"],
      "typical_stance": "chipset and platform focused, pragmatic",
      "typical_delegate_share": 0.04
    },
    {
      "name": "Apple",
      "short_name": "APPL",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["RAN2", "SA1", "CT1"],
      "typical_stance": "device and user experience focused, protective of UE interests",
      "typical_delegate_share": 0.04
    },
    {
      "name": "MediaTek",
      "short_name": "MTK",
      "region": "APAC",
      "country": "Taiwan",
      "typical_wgs": ["RAN1", "RAN2"],
      "typical_stance": "chipset vendor, cost-efficiency focus",
      "typical_delegate_share": 0.04
    },
    {
      "name": "OPPO",
      "short_name": "OPP",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["RAN2", "SA1"],
      "typical_stance": "device manufacturer, feature and UX driven",
      "typical_delegate_share": 0.04
    },
    {
      "name": "vivo",
      "short_name": "VIV",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["RAN2", "SA1"],
      "typical_stance": "device manufacturer, emerging standards contributor",
      "typical_delegate_share": 0.03
    },
    {
      "name": "Google",
      "short_name": "GOOG",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["SA1", "SA2", "CT1"],
      "typical_stance": "cloud and platform focus, open standards advocate",
      "typical_delegate_share": 0.03
    },
    {
      "name": "AT&T",
      "short_name": "ATT",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["SA1", "SA2", "RAN3"],
      "typical_stance": "operator perspective, service and deployment focused",
      "typical_delegate_share": 0.03
    },
    {
      "name": "T-Mobile",
      "short_name": "TMO",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["SA1", "RAN2", "RAN3"],
      "typical_stance": "operator, spectrum and deployment efficiency focus",
      "typical_delegate_share": 0.02
    },
    {
      "name": "China Mobile",
      "short_name": "CMCC",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["SA1", "SA2", "RAN3"],
      "typical_stance": "operator, large-scale deployment and network slicing focus",
      "typical_delegate_share": 0.04
    },
    {
      "name": "CATT",
      "short_name": "CATT",
      "region": "CN",
      "country": "China",
      "typical_wgs": ["RAN1", "SA1", "SA2"],
      "typical_stance": "Chinese research institute, aligned with CN operator interests",
      "typical_delegate_share": 0.03
    },
    {
      "name": "KDDI",
      "short_name": "KDDI",
      "region": "APAC",
      "country": "Japan",
      "typical_wgs": ["SA1", "SA2", "RAN2"],
      "typical_stance": "Japanese operator, service evolution and quality focus",
      "typical_delegate_share": 0.02
    },
    {
      "name": "NTT DOCOMO",
      "short_name": "DOCOM",
      "region": "APAC",
      "country": "Japan",
      "typical_wgs": ["SA1", "SA2", "RAN1"],
      "typical_stance": "Japanese operator, strong on 5G evolution and services",
      "typical_delegate_share": 0.02
    },
    {
      "name": "Deutsche Telekom",
      "short_name": "DT",
      "region": "EU",
      "country": "Germany",
      "typical_wgs": ["SA1", "SA2", "RAN3"],
      "typical_stance": "European operator, network virtualisation and slice focus",
      "typical_delegate_share": 0.02
    },
    {
      "name": "Orange",
      "short_name": "ORA",
      "region": "EU",
      "country": "France",
      "typical_wgs": ["SA1", "SA2"],
      "typical_stance": "European operator, security and privacy advocate",
      "typical_delegate_share": 0.02
    },
    {
      "name": "Vodafone",
      "short_name": "VOD",
      "region": "EU",
      "country": "UK",
      "typical_wgs": ["SA1", "SA2", "RAN3"],
      "typical_stance": "operator, IoT and enterprise 5G focus",
      "typical_delegate_share": 0.02
    },
    {
      "name": "InterDigital",
      "short_name": "IDC",
      "region": "US",
      "country": "United States",
      "typical_wgs": ["RAN1", "RAN2"],
      "typical_stance": "IPR-heavy, strong physical layer research contributor",
      "typical_delegate_share": 0.02
    },
    {
      "name": "Sharp",
      "short_name": "SHRP",
      "region": "APAC",
      "country": "Japan",
      "typical_wgs": ["RAN1", "RAN2"],
      "typical_stance": "device manufacturer, UE feature focused",
      "typical_delegate_share": 0.01
    },
    {
      "name": "Panasonic",
      "short_name": "PAN",
      "region": "APAC",
      "country": "Japan",
      "typical_wgs": ["SA3", "CT1"],
      "typical_stance": "security and IoT device focused",
      "typical_delegate_share": 0.01
    },
    {
      "name": "LG Electronics",
      "short_name": "LGE",
      "region": "APAC",
      "country": "South Korea",
      "typical_wgs": ["RAN1", "RAN2", "SA1"],
      "typical_stance": "device manufacturer, 5G feature and UE capability focus",
      "typical_delegate_share": 0.01
    }
  ],
  "working_groups": {
    "RAN1": "Radio layer 1 — physical layer specifications",
    "RAN2": "Radio layer 2 and 3 — RLC, MAC, RRC protocols",
    "RAN3": "Radio network architecture — X2/Xn, NG interfaces",
    "SA1": "Services and system aspects — requirements",
    "SA2": "System architecture",
    "SA3": "Security",
    "CT1": "Core network protocols — NAS, CC",
    "CT4": "Subscriber data management"
  }
}
```

- [ ] **Step 2: Verify the file loads as valid JSON**

```bash
python3 -c "import json; d=json.load(open('backend/app/data/3gpp_companies.json')); print(f'{len(d[\"companies\"])} companies, shares sum={sum(c[\"typical_delegate_share\"] for c in d[\"companies\"]):.2f}')"
```

Expected output: `25 companies, shares sum=1.00` (or close to 1.00)

- [ ] **Step 3: Commit**

```bash
git add backend/app/data/3gpp_companies.json
git commit -m "feat: add 3GPP company library data file"
```

---

### Task 2: SyntheticEntityNode and distribution dataclasses

**Files:**

- Create: `backend/app/services/synthetic_delegate_generator.py` (dataclasses only for now)
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_synthetic_delegate_generator.py`

- [ ] **Step 1: Write failing tests for dataclasses**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/test_synthetic_delegate_generator.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` — the module doesn't exist yet.

- [ ] **Step 3: Create the dataclasses**

Create `backend/app/services/synthetic_delegate_generator.py`:

```python
"""
Synthetic 3GPP Delegate Generator.

Generates fictive but realistic 3GPP conference delegate profiles for simulation.
Two LLM calls: (1) infer company/WG distribution from documents,
(2) batch-generate delegate personas.
"""

import json
import math
import os
import random
import re
import uuid as uuid_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger, log_llm_interaction
from .oasis_profile_generator import OasisAgentProfile
from openai import OpenAI

logger = get_logger("mirofish.synthetic_delegate")


@dataclass
class CompanySpec:
    """A single company's delegate allocation for a simulation."""
    name: str
    short_name: str
    region: str
    country: str
    delegate_count: int
    typical_wgs: List[str]
    typical_stance: str


@dataclass
class DelegateDistribution:
    """Full delegate distribution for a simulation run."""
    companies: List[CompanySpec]
    working_groups: List[str]
    topic_context: str
    total_delegates: int


@dataclass
class SyntheticEntityNode:
    """
    Duck-typed compatible with EntityNode so it flows through
    SimulationConfigGenerator and OasisProfileGenerator unchanged.
    """
    uuid: str
    name: str
    entity_type: str = "Delegate"
    summary: str = ""
    # EntityNode interface — required fields
    labels: List[str] = field(default_factory=lambda: ["Delegate"])
    attributes: Dict[str, Any] = field(default_factory=dict)
    related_edges: List[Any] = field(default_factory=list)
    related_nodes: List[Any] = field(default_factory=list)
    # 3GPP-specific fields
    company: str = ""
    working_group: str = ""
    expertise: str = ""
    delegate_role: str = "delegate"
    seniority: str = "senior engineer"
    stance: str = "neutral"

    def get_entity_type(self) -> str:
        """Required by SimulationConfigGenerator and OasisProfileGenerator callers."""
        return self.entity_type
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestSyntheticEntityNode tests/test_synthetic_delegate_generator.py::TestCompanySpec tests/test_synthetic_delegate_generator.py::TestDelegateDistribution -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/synthetic_delegate_generator.py backend/tests/__init__.py backend/tests/test_synthetic_delegate_generator.py
git commit -m "feat: add SyntheticEntityNode and distribution dataclasses"
```

---

## Chunk 2: SyntheticDelegateGenerator Service

### Task 3: Company library loader and distribution builder

**Files:**

- Modify: `backend/app/services/synthetic_delegate_generator.py`
- Modify: `backend/tests/test_synthetic_delegate_generator.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_synthetic_delegate_generator.py`:

```python
from backend.app.services.synthetic_delegate_generator import SyntheticDelegateGenerator


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestCompanyLibrary tests/test_synthetic_delegate_generator.py::TestBuildDistributionFromManual tests/test_synthetic_delegate_generator.py::TestBuildDistributionFromPresets -v 2>&1 | head -20
```

Expected: `AttributeError` — methods not yet defined.

- [ ] **Step 3: Implement the methods**

Add to `backend/app/services/synthetic_delegate_generator.py` after the dataclasses:

```python

class SyntheticDelegateGenerator:
    """Generate synthetic 3GPP delegate profiles for simulation."""

    BATCH_SIZE = 20
    MAX_PARALLEL = 5

    # Fallback name pool for rule-based generation
    _FIRST_NAMES = [
        "Lena", "Thomas", "Yuki", "Carlos", "Mei", "James", "Fatima",
        "Henrik", "Priya", "Lars", "Sarah", "Wei", "Alex", "Maria", "Jin",
        "Emma", "David", "Aiko", "Lucas", "Nina", "Oliver", "Hana",
    ]
    _LAST_NAMES = [
        "Berg", "Müller", "Tanaka", "Garcia", "Zhang", "Smith", "Al-Hassan",
        "Andersen", "Sharma", "Eriksson", "Johnson", "Li", "Novak", "Rossi",
        "Kim", "Johansson", "Chen", "Fischer", "Okonkwo", "Svensson",
    ]
    _MBTI = [
        "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
    ]

    def __init__(self, llm_client=None):
        self.company_library = self._load_company_library()
        # Reuse existing LLMClient pattern
        self._api_key = Config.LLM_API_KEY
        self._base_url = Config.LLM_BASE_URL
        self._model = Config.LLM_MODEL_NAME
        if llm_client:
            self._llm = llm_client
        else:
            self._llm = OpenAI(api_key=self._api_key, base_url=self._base_url)

    def _load_company_library(self) -> Dict[str, Any]:
        path = os.path.join(os.path.dirname(__file__), "../data/3gpp_companies.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Distribution building
    # ------------------------------------------------------------------

    def _build_distribution_from_manual(
        self,
        manual_config: Dict[str, Any],
        total_delegates: int,
        simulation_requirement: str,
    ) -> DelegateDistribution:
        """Validate and convert a manual config dict into a DelegateDistribution."""
        required = {"name", "delegate_count", "typical_wgs"}
        companies = []
        for entry in manual_config.get("companies", []):
            missing = required - entry.keys()
            if missing:
                raise ValueError(f"Company entry missing required field: {missing}")
            if entry["delegate_count"] <= 0:
                raise ValueError(
                    f"delegate_count must be positive, got {entry['delegate_count']} for {entry.get('name')}"
                )
            companies.append(
                CompanySpec(
                    name=entry["name"],
                    short_name=entry.get("short_name", entry["name"][:4].upper()),
                    region=entry.get("region", "EU"),
                    country=entry.get("country", ""),
                    delegate_count=entry["delegate_count"],
                    typical_wgs=entry["typical_wgs"],
                    typical_stance=entry.get("typical_stance", "neutral"),
                )
            )
        # Rescale if sum differs from total_delegates
        current_sum = sum(c.delegate_count for c in companies)
        if current_sum != total_delegates and current_sum > 0:
            companies = self._rescale_counts(companies, total_delegates)
        all_wgs: List[str] = []
        for c in companies:
            for wg in c.typical_wgs:
                if wg not in all_wgs:
                    all_wgs.append(wg)
        return DelegateDistribution(
            companies=companies,
            working_groups=all_wgs,
            topic_context=simulation_requirement,
            total_delegates=total_delegates,
        )

    def _build_distribution_from_presets(
        self, total_delegates: int, topic_context: str
    ) -> DelegateDistribution:
        """Build a distribution from the preset library using share weights."""
        lib_companies = self.company_library["companies"]
        # For very small totals, take top-N companies by share (1 delegate each)
        if total_delegates < 5:
            sorted_cos = sorted(lib_companies, key=lambda c: c["typical_delegate_share"], reverse=True)
            selected = sorted_cos[:total_delegates]
            companies = [
                CompanySpec(
                    name=c["name"], short_name=c["short_name"], region=c["region"],
                    country=c["country"], delegate_count=1,
                    typical_wgs=c["typical_wgs"], typical_stance=c["typical_stance"],
                )
                for c in selected
            ]
        else:
            # Take top-N where N = min(total_delegates, len(library))
            n_companies = min(total_delegates, len(lib_companies))
            sorted_cos = sorted(lib_companies, key=lambda c: c["typical_delegate_share"], reverse=True)
            selected = sorted_cos[:n_companies]
            companies = [
                CompanySpec(
                    name=c["name"], short_name=c["short_name"], region=c["region"],
                    country=c["country"],
                    delegate_count=max(1, round(c["typical_delegate_share"] * total_delegates)),
                    typical_wgs=c["typical_wgs"], typical_stance=c["typical_stance"],
                )
                for c in selected
            ]
            companies = self._rescale_counts(companies, total_delegates)
        all_wgs: List[str] = []
        for c in companies:
            for wg in c.typical_wgs:
                if wg not in all_wgs:
                    all_wgs.append(wg)
        return DelegateDistribution(
            companies=companies,
            working_groups=all_wgs,
            topic_context=topic_context,
            total_delegates=total_delegates,
        )

    @staticmethod
    def _rescale_counts(companies: List[CompanySpec], target: int) -> List[CompanySpec]:
        """
        Rescale delegate_count values proportionally to sum exactly to target.
        Rounding residuals are added to / subtracted from the company with the
        highest delegate_count.
        """
        current = sum(c.delegate_count for c in companies)
        if current == 0:
            return companies
        scaled = [max(1, round(c.delegate_count / current * target)) for c in companies]
        diff = target - sum(scaled)
        if diff != 0:
            # Apply residual to largest-count company
            max_idx = scaled.index(max(scaled))
            scaled[max_idx] += diff
        result = []
        for i, company in enumerate(companies):
            result.append(CompanySpec(
                name=company.name, short_name=company.short_name,
                region=company.region, country=company.country,
                delegate_count=scaled[i],
                typical_wgs=company.typical_wgs,
                typical_stance=company.typical_stance,
            ))
        return result
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestCompanyLibrary tests/test_synthetic_delegate_generator.py::TestBuildDistributionFromManual tests/test_synthetic_delegate_generator.py::TestBuildDistributionFromPresets -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/synthetic_delegate_generator.py backend/tests/test_synthetic_delegate_generator.py
git commit -m "feat: add company library loader and distribution builder"
```

---

### Task 4: Distribution inference (LLM Call 1)

**Files:**

- Modify: `backend/app/services/synthetic_delegate_generator.py`
- Modify: `backend/tests/test_synthetic_delegate_generator.py`

- [ ] **Step 1: Write failing tests (with LLM mocked)**

Add to `backend/tests/test_synthetic_delegate_generator.py`:

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestInferDistribution -v 2>&1 | head -20
```

Expected: `AttributeError` — `infer_distribution` not yet defined.

- [ ] **Step 3: Implement `infer_distribution`**

Add to `SyntheticDelegateGenerator` class in `backend/app/services/synthetic_delegate_generator.py`:

```python
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer_distribution(
        self,
        document_text: str,
        simulation_requirement: str,
        total_delegates: int,
        manual_config: Optional[Dict[str, Any]] = None,
    ) -> DelegateDistribution:
        """
        LLM Call 1: infer company/WG distribution from documents.
        Skipped if manual_config is provided.
        Falls back to preset library if LLM fails.
        """
        if manual_config:
            return self._build_distribution_from_manual(
                manual_config, total_delegates, simulation_requirement
            )
        try:
            return self._infer_distribution_with_llm(
                document_text, simulation_requirement, total_delegates
            )
        except Exception as e:
            logger.warning(f"LLM distribution inference failed: {e}. Falling back to presets.")
            return self._build_distribution_from_presets(total_delegates, simulation_requirement)

    def _infer_distribution_with_llm(
        self,
        document_text: str,
        simulation_requirement: str,
        total_delegates: int,
    ) -> DelegateDistribution:
        company_list_json = json.dumps(
            [{"name": c["name"], "short_name": c["short_name"], "region": c["region"],
              "country": c["country"], "typical_wgs": c["typical_wgs"],
              "typical_stance": c["typical_stance"],
              "typical_delegate_share": c["typical_delegate_share"]}
             for c in self.company_library["companies"]],
            ensure_ascii=False
        )
        system_prompt = (
            "You are a 3GPP standardization expert. Analyze the provided documents and "
            "determine which companies are most relevant to the debate, then allocate "
            f"{total_delegates} delegate slots across companies. "
            "Output valid JSON only — no markdown, no commentary."
        )
        user_prompt = (
            f"## Simulation Requirement\n{simulation_requirement}\n\n"
            f"## Document Excerpt\n{document_text[:8000]}\n\n"
            f"## Available Companies (reference only — you may use any subset)\n{company_list_json}\n\n"
            "Output JSON with this exact structure:\n"
            "{\n"
            '  "topic_context": "<one sentence summary of the debate>",\n'
            '  "companies": [\n'
            '    {"name": "...", "short_name": "...", "region": "...", "country": "...",\n'
            '     "delegate_count": <int>, "typical_wgs": ["..."], "typical_stance": "..."}\n'
            "  ]\n"
            "}\n"
            f"Total delegate_count values must sum to exactly {total_delegates}."
        )
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if Config.LLM_JSON_MODE:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._llm.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip(), flags=re.IGNORECASE)
        content = re.sub(r"\n?```\s*$", "", content)
        parsed = json.loads(content.strip())
        log_llm_interaction(
            source_file="synthetic_delegate_generator.py",
            messages=kwargs["messages"],
            response_text=content,
        )
        companies = [
            CompanySpec(
                name=c["name"], short_name=c.get("short_name", c["name"][:4].upper()),
                region=c.get("region", "EU"), country=c.get("country", ""),
                delegate_count=c["delegate_count"],
                typical_wgs=c.get("typical_wgs", []),
                typical_stance=c.get("typical_stance", "neutral"),
            )
            for c in parsed.get("companies", [])
        ]
        # Rescale to ensure exact sum
        if companies:
            companies = self._rescale_counts(companies, total_delegates)
        all_wgs: List[str] = []
        for c in companies:
            for wg in c.typical_wgs:
                if wg not in all_wgs:
                    all_wgs.append(wg)
        return DelegateDistribution(
            companies=companies,
            working_groups=all_wgs,
            topic_context=parsed.get("topic_context", simulation_requirement),
            total_delegates=total_delegates,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestInferDistribution -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/synthetic_delegate_generator.py backend/tests/test_synthetic_delegate_generator.py
git commit -m "feat: implement distribution inference (LLM Call 1)"
```

---

### Task 5: Delegate profile generation (LLM Call 2 + rule-based fallback)

**Files:**

- Modify: `backend/app/services/synthetic_delegate_generator.py`
- Modify: `backend/tests/test_synthetic_delegate_generator.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_synthetic_delegate_generator.py`:

```python
from backend.app.services.synthetic_delegate_generator import SyntheticDelegateGenerator


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py::TestRuleBasedBatch tests/test_synthetic_delegate_generator.py::TestGenerateMethod -v 2>&1 | head -20
```

Expected: `AttributeError` — methods not yet defined.

- [ ] **Step 3: Implement rule-based batch and `generate` method**

Add to `SyntheticDelegateGenerator` in `backend/app/services/synthetic_delegate_generator.py`:

```python
    def _generate_rule_based_batch(
        self,
        company: CompanySpec,
        count: int,
        id_offset: int,
    ) -> Tuple[List[OasisAgentProfile], List[SyntheticEntityNode]]:
        """Rule-based fallback when LLM batch fails."""
        profiles: List[OasisAgentProfile] = []
        nodes: List[SyntheticEntityNode] = []
        used_usernames: set = set()
        wg = company.typical_wgs[0] if company.typical_wgs else "RAN1"
        for i in range(count):
            first = random.choice(self._FIRST_NAMES)
            last = random.choice(self._LAST_NAMES)
            name = f"{first} {last}"
            base_username = f"{first.lower()}_{last.lower()}_{company.short_name.lower()}"
            username = base_username
            suffix = 1
            while username in used_usernames:
                username = f"{base_username}_{suffix}"
                suffix += 1
            used_usernames.add(username)
            profile = OasisAgentProfile(
                user_id=id_offset + i,
                user_name=username,
                name=name,
                bio=f"Engineer at {company.name}, {wg} delegate.",
                persona=(
                    f"You are {name}, an engineer at {company.name} specialising in {wg}. "
                    f"You participate in 3GPP standardization meetings and review technical "
                    f"proposals carefully. Your stance is neutral."
                ),
                age=random.randint(28, 55),
                gender=random.choice(["male", "female"]),
                mbti=random.choice(self._MBTI),
                country=company.country,
                profession=f"Standards Engineer at {company.name}",
                interested_topics=[wg],
                karma=random.randint(500, 2000),
                follower_count=random.randint(50, 500),
                source_entity_type="Delegate",
            )
            # Embed 3GPP metadata into profile for downstream use
            profile.company = company.name  # type: ignore[attr-defined]
            profiles.append(profile)
            node = SyntheticEntityNode(
                uuid=str(uuid_lib.uuid4()),
                name=name,
                summary=profile.bio,
                company=company.name,
                working_group=wg,
                expertise=wg,
                delegate_role="delegate",
                seniority="engineer",
                stance="neutral",
            )
            nodes.append(node)
        return profiles, nodes

    def _generate_llm_batch(
        self,
        company: CompanySpec,
        count: int,
        id_offset: int,
        topic_context: str,
        document_text: str,
    ) -> Tuple[List[OasisAgentProfile], List[SyntheticEntityNode]]:
        """One LLM Call 2 batch for a single company."""
        wgs_str = ", ".join(company.typical_wgs) or "RAN1"
        system_prompt = (
            "You are a 3GPP standardization expert. Generate realistic delegate profiles "
            "for a simulation. Output a JSON array only — no markdown, no commentary."
        )
        user_prompt = (
            f"Generate exactly {count} delegate profiles for {company.name} "
            f"({company.short_name}, {company.region}).\n"
            f"Topic context: {topic_context}\n"
            f"Typical working groups: {wgs_str}\n"
            f"Company stance: {company.typical_stance}\n\n"
            f"Document excerpt (for context):\n{document_text[:3000]}\n\n"
            "Return a JSON array where each element has:\n"
            '{"name": "...", "username": "...", "bio": "...", '
            '"persona": "You are <name>, <rich background including company, WG, expertise, '
            'stance relevant to the debate topic>...", '
            '"age": int, "gender": "male|female|non-binary", "mbti": "...", '
            f'"country": "{company.country}", '
            '"company": "...", "working_group": "...", '
            '"expertise_areas": ["..."], '
            '"delegate_role": "delegate|rapporteur|chair|observer", '
            '"seniority": "junior engineer|senior engineer|principal engineer|fellow", '
            '"stance": "...", "karma": int, "follower_count": int}'
        )
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        if Config.LLM_JSON_MODE:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._llm.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip(), flags=re.IGNORECASE)
        content = re.sub(r"\n?```\s*$", "", content)
        log_llm_interaction(
            source_file="synthetic_delegate_generator.py",
            messages=kwargs["messages"],
            response_text=content,
        )
        # Parse — may be array or {"delegates": [...]} object
        parsed = json.loads(content.strip())
        if isinstance(parsed, dict):
            items = parsed.get("delegates", parsed.get("profiles", list(parsed.values())[0]))
        else:
            items = parsed
        profiles: List[OasisAgentProfile] = []
        nodes: List[SyntheticEntityNode] = []
        for i, d in enumerate(items[:count]):
            profile = OasisAgentProfile(
                user_id=id_offset + i,
                user_name=d.get("username", f"del_{id_offset+i}_{company.short_name.lower()}"),
                name=d.get("name", f"Delegate {id_offset+i}"),
                bio=d.get("bio", f"Engineer at {company.name}"),
                persona=d.get("persona", f"You are an engineer at {company.name}."),
                age=d.get("age"),
                gender=d.get("gender"),
                mbti=d.get("mbti"),
                country=d.get("country", company.country),
                profession=d.get("seniority", "engineer") + f" at {company.name}",
                interested_topics=d.get("expertise_areas", []),
                karma=d.get("karma", 1000),
                follower_count=d.get("follower_count", 100),
                source_entity_type="Delegate",
            )
            profile.company = company.name  # type: ignore[attr-defined]
            profiles.append(profile)
            node = SyntheticEntityNode(
                uuid=str(uuid_lib.uuid4()),
                name=profile.name,
                summary=profile.bio,
                company=company.name,
                working_group=d.get("working_group", company.typical_wgs[0] if company.typical_wgs else ""),
                expertise=", ".join(d.get("expertise_areas", [])),
                delegate_role=d.get("delegate_role", "delegate"),
                seniority=d.get("seniority", "senior engineer"),
                stance=d.get("stance", "neutral"),
            )
            nodes.append(node)
        # Pad to count with rule-based if LLM returned fewer
        if len(profiles) < count:
            rb_profiles, rb_nodes = self._generate_rule_based_batch(
                company, count - len(profiles), id_offset + len(profiles)
            )
            profiles.extend(rb_profiles)
            nodes.extend(rb_nodes)
        return profiles, nodes

    def generate(
        self,
        distribution: DelegateDistribution,
        document_text: str,
        simulation_requirement: str,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[List[SyntheticEntityNode], List[OasisAgentProfile]]:
        """
        LLM Call 2: batch-generate delegate profiles for all companies.
        Returns (SyntheticEntityNode list, OasisAgentProfile list).
        """
        all_profiles: List[OasisAgentProfile] = []
        all_nodes: List[SyntheticEntityNode] = []
        total = distribution.total_delegates
        completed = 0
        id_offset = 0

        def _process_company(company: CompanySpec) -> Tuple[List[OasisAgentProfile], List[SyntheticEntityNode]]:
            try:
                p, n = self._generate_llm_batch(
                    company, company.delegate_count, id_offset, distribution.topic_context, document_text
                )
                return p, n
            except Exception as e:
                logger.warning(f"LLM batch failed for {company.name}: {e}. Retrying once...")
                try:
                    p, n = self._generate_llm_batch(
                        company, company.delegate_count, id_offset, distribution.topic_context, document_text
                    )
                    return p, n
                except Exception as e2:
                    logger.warning(f"Retry failed for {company.name}: {e2}. Using rule-based fallback.")
                    return self._generate_rule_based_batch(company, company.delegate_count, id_offset)

        # Process companies sequentially to manage id_offset correctly
        # (parallelism within a batch is handled by the LLM call itself)
        for company in distribution.companies:
            profiles, nodes = _process_company(company)
            # Re-assign user IDs sequentially from current offset
            for i, p in enumerate(profiles):
                p.user_id = id_offset + i
            for i, n in enumerate(nodes):
                pass  # uuid is already unique
            all_profiles.extend(profiles)
            all_nodes.extend(nodes)
            id_offset += len(profiles)
            completed += len(profiles)
            if progress_callback:
                progress_callback(completed, total, f"Generated delegates for {company.name}")
        return all_nodes, all_profiles
```

**Note — Parallelism deferred:** `BATCH_SIZE = 20` and `MAX_PARALLEL = 5` are defined as class constants but the current `generate()` implementation processes companies sequentially. This is intentional to keep `id_offset` management simple. Intra-company parallelism (splitting large companies into sub-batches of 20 and running 5 concurrent) is deferred as technical debt — the constants are placeholders for that future work.

- [ ] **Step 4: Run all tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_synthetic_delegate_generator.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/synthetic_delegate_generator.py backend/tests/test_synthetic_delegate_generator.py
git commit -m "feat: implement delegate batch generation with LLM + rule-based fallback"
```

---

## Chunk 3: SimulationConfigGenerator and SimulationManager Integration

### Task 6: Add "delegate" rule case to SimulationConfigGenerator

**Files:**

- Modify: `backend/app/services/simulation_config_generator.py` (lines ~913–994 and imports)
- Create: `backend/tests/test_simulation_config_delegate.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_simulation_config_delegate.py`:

```python
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
        # Conference hours: 8–17 (not Chinese evening peak)
        assert 8 in cfg["active_hours"]
        assert 17 in cfg["active_hours"]
        # Must NOT use Chinese evening peak (21, 22, 23 should not be primary hours)
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_simulation_config_delegate.py -v 2>&1 | head -20
```

Expected: `AssertionError` — delegate type falls into the `else` branch.

- [ ] **Step 3: Add the delegate rule case**

In `backend/app/services/simulation_config_generator.py`, in the `_generate_agent_config_by_rule` method (line ~913), add a new branch before the final `else`:

```python
        elif entity_type in ["delegate", "rapporteur", "chair", "observer"]:
            # 3GPP conference delegates: daytime conference hours, focused discussion
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.2,
                "comments_per_hour": 0.8,
                "active_hours": list(range(8, 18)),  # 08:00-17:59 conference hours
                "response_delay_min": 10,
                "response_delay_max": 60,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.5
            }
```

Also update the type annotation on line ~252:

```python
# Change:
        entities: List[EntityNode],
# To:
        entities: List[Union[EntityNode, "SyntheticEntityNode"]],
```

Add `Union` to the imports at the top of `simulation_config_generator.py`:

```python
from typing import Dict, Any, List, Optional, Callable, Union
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_simulation_config_delegate.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulation_config_generator.py backend/tests/test_simulation_config_delegate.py
git commit -m "feat: add delegate rule-based config and Union type annotation"
```

---

### Task 7: Integrate into SimulationManager.prepare_simulation

**Files:**

- Modify: `backend/app/services/simulation_manager.py`

- [ ] **Step 1: Add the import**

At the top of `backend/app/services/simulation_manager.py`, add:

```python
from .synthetic_delegate_generator import SyntheticDelegateGenerator
```

- [ ] **Step 2: Update `prepare_simulation` signature**

Replace the existing signature (line 229) with:

```python
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[Callable] = None,
        parallel_profile_count: int = 3,
        enable_synthetic_delegates: bool = True,
        synthetic_delegate_count: int = 30,
        synthetic_delegate_config: Optional[Dict[str, Any]] = None,
    ) -> SimulationState:
```

Note: use `Callable` (capital C, from `typing`) for consistency with the codebase.

- [ ] **Step 3: Initialise synthetic_nodes/profiles and run Stage 1.5**

**Important — Replace mode:** The current code at line 297-301 returns early with `FAILED` status when `filtered.filtered_count == 0`. In Replace mode (no Zep entities), this would abort before synthetic delegates are generated. Add Stage 1.5 **before** the empty-entity guard so it runs in all modes:

Insert **between line 269 (`sim_dir = ...`) and line 271 (Stage 1 comment)**:

```python
            # ========== Stage 1.5 init — always run regardless of entity count ==========
            synthetic_nodes = []
            synthetic_profiles = []
```

Then **after** the `if filtered.filtered_count == 0:` block (line ~301), add the generation logic:

```python
            # ========== Stage 1.5: Synthetic delegate generation ==========
            if enable_synthetic_delegates:
                if progress_callback:
                    progress_callback(
                        "generating_delegates", 0,
                        "Inferring 3GPP delegate distribution...",
                        current=0, total=synthetic_delegate_count
                    )
                delegate_gen = SyntheticDelegateGenerator()
                distribution = delegate_gen.infer_distribution(
                    document_text=document_text,
                    simulation_requirement=simulation_requirement,
                    total_delegates=synthetic_delegate_count,
                    manual_config=synthetic_delegate_config,
                )

                def delegate_progress(current, total, msg):
                    if progress_callback:
                        progress_callback(
                            "generating_delegates",
                            int(current / max(total, 1) * 100),
                            msg,
                            current=current, total=total
                        )

                synthetic_nodes, synthetic_profiles = delegate_gen.generate(
                    distribution=distribution,
                    document_text=document_text,
                    simulation_requirement=simulation_requirement,
                    progress_callback=delegate_progress,
                )
                logger.info(
                    f"Synthetic delegate generation complete: {len(synthetic_nodes)} delegates"
                )
                if progress_callback:
                    progress_callback(
                        "generating_delegates", 100,
                        f"Generated {len(synthetic_nodes)} synthetic delegates",
                        current=len(synthetic_nodes), total=len(synthetic_nodes)
                    )
```

**Also update the empty-entity guard** at line 297-301 to allow Replace mode to continue:

```python
            if filtered.filtered_count == 0 and not enable_synthetic_delegates:
                state.status = SimulationStatus.FAILED
                state.error = "No matching entities found. Please check whether the graph was built correctly"
                self._save_simulation_state(state)
                return state
```

- [ ] **Step 4: Merge profiles BEFORE saving (critical ordering)**

After Stage 2 generates profiles (line ~346 `profiles = generator.generate_profiles_from_entities(...)`) and **BEFORE the `save_profiles` calls at lines 374-387**, insert:

```python
            # Merge synthetic profiles — must happen before save_profiles calls
            for i, sp in enumerate(synthetic_profiles):
                sp.user_id = len(profiles) + i
            profiles = profiles + synthetic_profiles
            state.profiles_count = len(profiles)
```

The existing `save_profiles` calls at lines 374-387 and the `state.profiles_count = len(profiles)` at line 362 do **not** need any other changes — `profiles` is now the merged list.

- [ ] **Step 5: Pass merged entities to generate_config**

On line ~422, change:

```python
                entities=filtered.entities,
```

To:

```python
                entities=filtered.entities + synthetic_nodes,
```

- [ ] **Step 6: Smoke test — start the backend and check /api/simulation/prepare accepts new params**

```bash
cd backend && python -c "
from app.services.simulation_manager import SimulationManager
import inspect
sig = inspect.signature(SimulationManager.prepare_simulation)
params = list(sig.parameters.keys())
assert 'enable_synthetic_delegates' in params, f'Missing param, got: {params}'
assert 'synthetic_delegate_count' in params
assert 'synthetic_delegate_config' in params
print('OK — new params present in signature')
"
```

Expected: `OK — new params present in signature`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/simulation_manager.py
git commit -m "feat: integrate synthetic delegate generation into prepare_simulation"
```

---

### Task 8: Update API endpoint

**Files:**

- Modify: `backend/app/api/simulation.py`

- [ ] **Step 1: Add new params and fix stage_weights**

In `backend/app/api/simulation.py`, find the `/prepare` endpoint handler. After where existing params are extracted from the request JSON (look for `use_llm_for_profiles = data.get(...)`), add:

```python
        enable_synthetic_delegates = data.get('enable_synthetic_delegates', True)
        synthetic_delegate_count = data.get('synthetic_delegate_count', 30)
        synthetic_delegate_config = data.get('synthetic_delegate_config', None)
```

Then pass them to `SimulationManager.prepare_simulation(...)` wherever it is called:

```python
                enable_synthetic_delegates=enable_synthetic_delegates,
                synthetic_delegate_count=synthetic_delegate_count,
                synthetic_delegate_config=synthetic_delegate_config,
```

**Also update `stage_weights`** (look for the dict with `"reading"`, `"generating_profiles"`, etc. in the progress callback closure). Add the new stage and rebalance weights:

```python
stage_weights = {
    "reading": (0, 15),
    "generating_delegates": (15, 40),
    "generating_profiles": (40, 70),
    "generating_config": (70, 90),
    "copying_scripts": (90, 100),
}
```

Without this, passing `"generating_delegates"` as the stage name causes a `ValueError` (stage not in dict) or incorrect progress values.

**Note on `force_regenerate`:** This param is already extracted from the request body in the existing endpoint code but is not forwarded to `prepare_simulation()`. Do not replicate this bug for the new params — forward all three new params explicitly as shown above.

- [ ] **Step 2: Smoke test the endpoint signature**

```bash
cd backend && python -c "
from app import create_app
app = create_app()
with app.test_client() as c:
    # Missing simulation_id should return 400, not 500
    r = c.post('/api/simulation/prepare', json={})
    print('Status:', r.status_code, '— expected 400 or 401')
"
```

Expected: status 400 or 401 (not 500).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/simulation.py
git commit -m "feat: add synthetic delegate params to /prepare API endpoint"
```

---

## Chunk 4: Frontend

### Task 9: Add toggle and count input to simulation prep UI

**Note:** The frontend is **Vue 3 Composition API** (`.vue` files with `<script setup>`), not React. Use `ref()` not `useState`.

**Files:**

- Modify: `frontend/src/components/Step2EnvSetup.vue`

- [ ] **Step 1: Open the component**

Open `frontend/src/components/Step2EnvSetup.vue`. Find the `<script setup>` block and locate where `prepareSimulation` is called and where other form state refs are declared.

- [ ] **Step 2: Add reactive state**

In the `<script setup>` block, alongside other `ref()` declarations:

```js
const enableSyntheticDelegates = ref(true)
const syntheticDelegateCount = ref(30)
```

- [ ] **Step 3: Pass the new params in the API call**

Find the `prepareSimulation(...)` call and add:

```js
prepareSimulation({
  // ...existing params...
  enable_synthetic_delegates: enableSyntheticDelegates.value,
  synthetic_delegate_count: syntheticDelegateCount.value,
})
```

- [ ] **Step 4: Add the UI controls**

In the `<template>`, add alongside the existing simulation prep controls (parallel count input, etc.):

```html
<!-- Synthetic delegate toggle -->
<div class="form-group">
  <label>
    <input
      type="checkbox"
      :checked="enableSyntheticDelegates"
      @change="e => enableSyntheticDelegates = e.target.checked"
    />
    Add synthetic 3GPP delegates
  </label>
</div>

<div v-if="enableSyntheticDelegates" class="form-group">
  <label>
    Delegate count
    <input
      type="number"
      :min="1"
      :max="500"
      v-model.number="syntheticDelegateCount"
      style="width: 80px; margin-left: 8px"
    />
  </label>
</div>
```

- [ ] **Step 5: Verify frontend compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: add synthetic delegate toggle and count to simulation prep UI"
```

---

### Task 10: End-to-end smoke test

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 2: Start backend and frontend**

```bash
npm run dev
```

- [ ] **Step 3: Manual verification checklist**

Open `http://localhost:3000` and:

1. Upload a 3GPP document (any PDF/TXT mentioning standardization, companies, or technical proposals)
2. Build the knowledge graph
3. Navigate to "Prepare Simulation"
4. Confirm the "Add synthetic 3GPP delegates" toggle is visible and checked by default
5. Confirm the "Delegate count" input shows 30
6. Enable **force_regenerate** (or use a fresh simulation) to bypass the `already_prepared` fast-path
7. Click Prepare
8. Watch the progress — confirm a "Generating delegates" stage appears in the progress bar
9. After completion, check the backend logs for: `Synthetic delegate generation complete: 30 delegates`
10. Check `backend/uploads/simulations/<sim_id>/reddit_profiles.json` — confirm it contains more entries than graph entities alone
11. Confirm at least one profile entry has a `persona` field referencing a 3GPP company name

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```
