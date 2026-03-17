# Synthetic 3GPP Delegate Generation — Design Spec

**Date:** 2026-03-17
**Status:** Approved
**Domain:** 3GPP Telecom Standardization Simulation

---

## Overview

MiroFish currently generates simulation agents exclusively from entities extracted from uploaded documents via the Zep knowledge graph. This feature adds the ability to generate synthetic 3GPP delegate agents — fictive but realistic conference participants with company affiliation, working group membership, technical expertise, role, seniority, and stance — to populate simulations with a larger, more representative delegate population.

---

## Goals

- Supplement real graph-entity agents with synthetic delegates during simulation prep
- Support full replacement mode (no Zep entities required)
- Default scale: ~30 synthetic delegates; configurable up to any number
- Each delegate is grounded in the simulation's 3GPP topic context via LLM generation
- Company/WG distribution is LLM-inferred from documents by default, manually overridable
- Preset company library is file-based and editable

---

## Pipeline Integration

Synthetic delegate generation runs inside `prepare_simulation()`, after real entity profile generation:

```
prepare_simulation()
  ├─ 1. ZepEntityReader → real entity profiles          (existing, mode A+C)
  ├─ 2. SyntheticDelegateGenerator.infer_distribution() (LLM Call 1, skipped if manual config provided)
  ├─ 3. SyntheticDelegateGenerator.generate_delegates() (LLM Call 2, batched + parallel)
  ├─ 4. Merge real + synthetic profiles → combined profile file
  └─ 5. SimulationConfigGenerator.generate_config(real + synthetic entities)
```

**Modes:**
- **Supplement (default):** Steps 1–5 all run. Synthetic delegates are added alongside real entities.
- **Replace:** Step 1 is skipped. Only synthetic delegates are used as agents.
- **Disabled:** Steps 2–4 skipped. Existing behaviour unchanged.

---

## New Components

### `SyntheticDelegateGenerator` service
**File:** `backend/app/services/synthetic_delegate_generator.py`

**Public interface:**
```python
class SyntheticDelegateGenerator:
    def infer_distribution(
        self,
        document_text: str,
        simulation_requirement: str,
        total_delegates: int,
        manual_config: Optional[Dict] = None,
    ) -> DelegateDistribution:
        """LLM Call 1. Skipped and replaced by manual_config if provided."""

    def generate_delegates(
        self,
        distribution: DelegateDistribution,
        document_text: str,
        simulation_requirement: str,
        progress_callback: Optional[Callable] = None,
    ) -> List[OasisAgentProfile]:
        """LLM Call 2. Batches of 20, parallelised."""
```

### Data structures

```python
@dataclass
class CompanySpec:
    name: str               # "Ericsson"
    short_name: str         # "ERX" — used in generated usernames
    region: str             # "EU" | "US" | "APAC" | "CN"
    country: str            # "Sweden"
    delegate_count: int
    typical_wgs: List[str]          # ["RAN1", "RAN2"]
    typical_stance: str             # free text hint for LLM

@dataclass
class DelegateDistribution:
    companies: List[CompanySpec]
    working_groups: List[str]
    topic_context: str      # LLM summary of the debate topic
    total_delegates: int

@dataclass
class SyntheticEntityNode:
    """Duck-typed as EntityNode so it flows through SimulationConfigGenerator unchanged."""
    uuid: str
    name: str
    entity_type: str = "Delegate"
    summary: str = ""
    # 3GPP-specific (embedded in persona for OASIS prompt injection)
    company: str = ""
    working_group: str = ""
    expertise: str = ""
    delegate_role: str = "delegate"     # delegate | rapporteur | chair | observer
    seniority: str = "senior engineer"
    stance: str = "neutral"
```

### Preset company library
**File:** `backend/app/data/3gpp_companies.json`

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
      "typical_stance": "standards-driven, strong on radio access",
      "typical_delegate_share": 0.10
    }
    // ~24 more: Nokia, Qualcomm, Apple, Samsung, Huawei, ZTE, Intel,
    // MediaTek, OPPO, vivo, Google, AT&T, T-Mobile, China Mobile, CATT,
    // KDDI, NTT DOCOMO, Deutsche Telekom, Orange, Vodafone, InterDigital,
    // Sharp, Panasonic, LG Electronics
  ],
  "working_groups": {
    "RAN1": "Radio layer 1 (physical layer)",
    "RAN2": "Radio layer 2 & 3",
    "RAN3": "Radio network architecture",
    "SA1": "Services and requirements",
    "SA2": "Architecture",
    "SA3": "Security",
    "CT1": "Core network protocols",
    "CT4": "Subscriber data management"
  }
}
```

`typical_delegate_share` is the fallback proportion used in pure synthetic mode. LLM inference overrides it based on document content.

---

## LLM Calls

### Call 1 — Distribution Inference

**When:** Default (C). Skipped when `synthetic_delegate_config` is provided manually.

**Input:** Document excerpts (truncated to 10k chars) + simulation requirement + preset company list as few-shot context.

**Output JSON:**
```json
{
  "companies": [
    {"name": "Ericsson", "short_name": "ERX", "region": "EU", "country": "Sweden",
     "delegate_count": 8, "typical_wgs": ["RAN1"], "typical_stance": "standards-driven"}
  ],
  "working_groups": ["RAN1", "RAN2"],
  "topic_context": "Debate on NR positioning accuracy requirements for Release 18..."
}
```

### Call 2 — Batch Profile Generation

**Batch size:** 20 delegates per call. Batches run in parallel (up to 5 concurrent).

**Output per delegate:**
```json
{
  "name": "Dr. Lena Berg",
  "username": "lena_berg_erx",
  "bio": "Principal Engineer at Ericsson, RAN1 delegate since 2012.",
  "persona": "You are Dr. Lena Berg, a Principal Engineer at Ericsson with 14 years in RAN1...",
  "age": 41,
  "gender": "female",
  "mbti": "INTJ",
  "country": "Sweden",
  "company": "Ericsson",
  "working_group": "RAN1",
  "expertise_areas": ["massive MIMO", "beam management", "NR positioning"],
  "delegate_role": "delegate",
  "seniority": "principal engineer",
  "stance": "skeptical of proposals lacking simulation results",
  "karma": 1200,
  "follower_count": 180
}
```

The `persona` field is the rich text OASIS injects into agent system prompts. It explicitly references the simulation topic so delegates behave contextually.

---

## API Changes

### `POST /api/simulation/prepare` — new optional fields

```json
{
  "simulation_id": "sim_xxx",
  "enable_synthetic_delegates": true,
  "synthetic_delegate_count": 30,
  "synthetic_delegate_config": null
}
```

`synthetic_delegate_config` structure (manual override, replaces LLM Call 1):
```json
{
  "companies": [
    {"name": "Ericsson", "short_name": "ERX", "region": "EU", "country": "Sweden",
     "delegate_count": 8, "typical_wgs": ["RAN1"], "typical_stance": "standards-driven"}
  ]
}
```

### Default values
| Parameter | Default |
|---|---|
| `enable_synthetic_delegates` | `true` |
| `synthetic_delegate_count` | `30` |
| `synthetic_delegate_config` | `null` (LLM-inferred) |

---

## Frontend Changes

The "Prepare Simulation" step gains two UI controls:

1. **Toggle:** "Add synthetic delegates" — on by default
2. **Number input:** "Delegate count" — default 30, visible when toggle is on

No UI for `synthetic_delegate_config` — manual company distribution is a power-user feature accessible via the API directly.

---

## Profile Merging

After generation, synthetic profiles are merged with real entity profiles before being written to the platform profile file (`reddit_profiles.json` / `twitter_profiles.csv`). `user_id` values for synthetic delegates start after the last real entity ID to avoid collisions.

---

## Out of Scope

- UI for editing the preset company library (file-based config only)
- Per-delegate stance editing in the UI
- Saving/reusing a generated delegate roster across simulations
