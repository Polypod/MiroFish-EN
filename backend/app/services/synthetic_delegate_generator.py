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
