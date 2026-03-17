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
        # Distribute residual one unit at a time to avoid dropping any company below 1
        while diff > 0:
            max_idx = scaled.index(max(scaled))
            scaled[max_idx] += 1
            diff -= 1
        while diff < 0:
            # Only reduce companies that have more than 1 delegate
            candidates = [i for i, v in enumerate(scaled) if v > 1]
            if not candidates:
                break
            max_idx = max(candidates, key=lambda i: scaled[i])
            scaled[max_idx] -= 1
            diff += 1
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
