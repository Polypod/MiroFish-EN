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

Synthetic delegate generation runs inside `prepare_simulation()` in `SimulationManager`, after real entity profile generation:

```
prepare_simulation(simulation_id, ..., enable_synthetic_delegates, synthetic_delegate_count, synthetic_delegate_config)
  ├─ 1. ZepEntityReader → real_entities          (skipped in Replace mode; also skip instantiation if ZEP_API_KEY absent)
  ├─ 2. SyntheticDelegateGenerator.infer_distribution()  (LLM Call 1; skipped if synthetic_delegate_config provided)
  ├─ 3. SyntheticDelegateGenerator.generate()
  │       └─ returns (synthetic_nodes: List[SyntheticEntityNode], synthetic_profiles: List[OasisAgentProfile])
  ├─ 4. OasisProfileGenerator.generate_profiles_from_entities(real_entities) → real_profiles
  ├─ 5. Merge profiles: merged = real_profiles + synthetic_profiles
  │       └─ user_id for synthetic delegates = len(real_profiles) + idx  (offset computed from in-memory list, not disk)
  │       └─ write merged list in single save_profiles() call (replaces any realtime-written interim file)
  └─ 6. SimulationConfigGenerator.generate_config(real_entities + synthetic_nodes)
```

**Modes:**

- **Supplement (default):** All steps run. Synthetic delegates added alongside real entities.
- **Replace:** Step 1 and `ZepEntityReader` instantiation are both skipped entirely. Only synthetic delegates are used.
- **Disabled:** Steps 2–3 skipped. `real_entities` used as before.

**ZEP_API_KEY in Replace mode:** `ZepEntityReader` construction is gated on mode — it is not instantiated when mode is Replace. This allows Replace mode to work without Zep credentials.

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
        """
        LLM Call 1. Returns a DelegateDistribution grounded in the documents.
        Skipped and replaced by manual_config if provided.
        total_delegates is passed in from the request, not derived from the LLM.
        topic_context is LLM-generated; working_groups is derived from typical_wgs
        across all returned companies.
        """

    def generate(
        self,
        distribution: DelegateDistribution,
        document_text: str,
        simulation_requirement: str,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[List[SyntheticEntityNode], List[OasisAgentProfile]]:
        """
        LLM Call 2. Returns BOTH:
        - SyntheticEntityNode list  → forwarded to SimulationConfigGenerator.generate_config()
        - OasisAgentProfile list    → merged into the platform profile file
        Batches of 20, parallelised (max 5 concurrent, matching existing pattern).
        On batch failure: retry once, then fall back to rule-based generation for that batch.
        """
```

### Data structures

```python
@dataclass
class CompanySpec:
    name: str               # "Ericsson"
    short_name: str         # "ERX" — used in generated usernames
    region: str             # "EU" | "US" | "APAC" | "CN"
    country: str            # "Sweden"
    delegate_count: int     # concrete count for this simulation (derived from typical_delegate_share * total)
    typical_wgs: List[str]          # ["RAN1", "RAN2"]
    typical_stance: str             # free text hint for LLM

@dataclass
class DelegateDistribution:
    companies: List[CompanySpec]
    working_groups: List[str]   # union of typical_wgs across all companies
    topic_context: str          # LLM-generated summary of the debate topic
    total_delegates: int        # passed in from request parameter, not from LLM

@dataclass
class SyntheticEntityNode:
    """
    Duck-typed compatible with EntityNode so it flows through
    SimulationConfigGenerator and OasisProfileGenerator unchanged.
    Required fields mirror EntityNode's interface.
    """
    uuid: str
    name: str
    entity_type: str = "Delegate"
    summary: str = ""
    # EntityNode interface requirements
    related_edges: List = field(default_factory=list)
    related_nodes: List = field(default_factory=list)
    labels: List[str] = field(default_factory=lambda: ["Delegate"])
    attributes: Dict = field(default_factory=dict)
    # 3GPP-specific (embedded in persona for OASIS prompt injection)
    company: str = ""
    working_group: str = ""
    expertise: str = ""
    delegate_role: str = "delegate"     # delegate | rapporteur | chair | observer
    seniority: str = "senior engineer"
    stance: str = "neutral"

    def get_entity_type(self) -> str:
        """Required by SimulationConfigGenerator and OasisProfileGenerator callers."""
        return self.entity_type
```

**Type annotation note:** `SimulationConfigGenerator.generate_config` is annotated `entities: List[EntityNode]`. The implementer must update this to `List[Union[EntityNode, SyntheticEntityNode]]`. Mypy will flag call sites otherwise.

### Rule-based config for Delegate type

`SimulationConfigGenerator._generate_agent_config_by_rule` must add a `"delegate"` case:

- Active hours: 08–18 (conference working hours, not Chinese evening defaults)
- Timezone: determined by delegate's `country`/`region` field
- Activity level: 0.6 (moderately active, focused on plenary sessions)
- Posting frequency: lower than media entities; more comments than posts

This ensures synthetic delegates don't inherit the Chinese evening-peak schedule hardcoded in current fallback/prompt defaults.

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

**`typical_delegate_share` → `delegate_count` conversion:**
In pure-synthetic mode (no LLM Call 1), only the top-N companies by `typical_delegate_share` are selected, where N = `total_delegates` (guaranteeing at least 1 delegate per company). `delegate_count` per selected company:

```python
delegate_count = max(1, round(typical_delegate_share * total_delegates))
```

Counts are then normalised to sum exactly to `total_delegates` by adding/removing from the largest company. If `total_delegates` < 5, only the top `total_delegates` companies (by share) are included, each assigned 1 delegate.

In LLM-inferred mode, the LLM outputs `delegate_count` directly per company; `typical_delegate_share` is provided as context only.

**`synthetic_delegate_config` validation:** If a manual config is provided, the backend validates it before use. Missing required fields (`name`, `delegate_count`, `typical_wgs`) return HTTP 400. If the sum of `delegate_count` values differs from `synthetic_delegate_count`, the values are rescaled proportionally to match.

---

## LLM Calls

### Call 1 — Distribution Inference

**When:** Default (C). Skipped when `synthetic_delegate_config` is provided manually.

**Input:** Document excerpts (truncated to 10k chars) + simulation requirement + preset company list as few-shot context.

**Output JSON:**
```json
{
  "topic_context": "Debate on NR positioning accuracy requirements for Release 18...",
  "companies": [
    {
      "name": "Ericsson", "short_name": "ERX", "region": "EU", "country": "Sweden",
      "delegate_count": 8, "typical_wgs": ["RAN1"], "typical_stance": "standards-driven"
    }
  ]
}
```

`working_groups` in `DelegateDistribution` is derived post-LLM as the union of all `typical_wgs` values.
`total_delegates` in `DelegateDistribution` is the request parameter — not derived from the LLM.

**Manual override mode:** When `synthetic_delegate_config` is provided, LLM Call 1 is skipped entirely. `working_groups` is derived from `typical_wgs` in the provided companies. `topic_context` is set to the `simulation_requirement` string verbatim.

### Call 2 — Batch Profile Generation

**Batch size:** 20 delegates per call. Batches run in parallel (up to 5 concurrent).
**Failure handling:** One retry per batch, then rule-based fallback for that batch.

**Rule-based fallback (when LLM batch fails):** Produces minimal but valid profiles using deterministic sampling:

- `name`: `"{FirstName} {LastName}"` sampled from a small built-in name list, prefixed with company short name to ensure uniqueness
- `username`: `"{first}_{last}_{short_name}".lower()`
- `bio`: `"Engineer at {company}, {working_group} delegate."`
- `persona`: `"You are {name}, an engineer at {company} specialising in {working_group}. You participate in 3GPP standardization meetings and review technical proposals carefully. Your stance is {stance}."`
- `age`: random int 28–55; `gender`: random; `mbti`: random from MBTI list; `country`: company's `country` field
- `expertise_areas`: `[working_group]` (single entry)
- `delegate_role`: `"delegate"`; `seniority`: `"engineer"`; `stance`: `"neutral"`
- `karma`/`follower_count`: random in realistic range (500–2000 / 50–500)

**Output per delegate:**
```json
{
  "name": "Dr. Lena Berg",
  "username": "lena_berg_erx",
  "bio": "Principal Engineer at Ericsson, RAN1 delegate since 2012.",
  "persona": "You are Dr. Lena Berg, a Principal Engineer at Ericsson with 14 years in RAN1. Your expertise is massive MIMO and beam management. You are pragmatic and data-driven, skeptical of proposals lacking simulation results. In this meeting you represent Ericsson's position on NR positioning accuracy...",
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

From each LLM output object, the service creates **both**:

- A `SyntheticEntityNode` (for the `generate_config` call)
- An `OasisAgentProfile` (for the profile file)

The `persona` field is the rich text OASIS injects into agent system prompts and explicitly references the simulation topic.

---

## API Changes

### `SimulationManager.prepare_simulation()` — updated signature

```python
def prepare_simulation(
    self,
    simulation_id: str,
    entity_types: Optional[List[str]] = None,
    use_llm_for_profiles: bool = True,
    parallel_profile_count: int = 5,
    force_regenerate: bool = False,
    enable_synthetic_delegates: bool = True,
    synthetic_delegate_count: int = 30,
    synthetic_delegate_config: Optional[Dict] = None,
    progress_callback: Optional[Callable] = None,
) -> None:
```

### `POST /api/simulation/prepare` — new optional request fields

```json
{
  "simulation_id": "sim_xxx",
  "enable_synthetic_delegates": true,
  "synthetic_delegate_count": 30,
  "synthetic_delegate_config": null
}
```

`synthetic_delegate_config` structure (manual override — replaces LLM Call 1):
```json
{
  "companies": [
    {
      "name": "Ericsson", "short_name": "ERX", "region": "EU", "country": "Sweden",
      "delegate_count": 8, "typical_wgs": ["RAN1"], "typical_stance": "standards-driven"
    }
  ]
}
```

When provided, `working_groups` is inferred from `typical_wgs` values; `topic_context` defaults to `simulation_requirement`.

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

No UI for `synthetic_delegate_config` — manual company distribution is a power-user feature accessible via the API.

---

## Profile Merging

After generation:

1. `real_profiles = OasisProfileGenerator.generate_profiles_from_entities(real_entities)` — IDs 0..N-1
2. `synthetic_profiles` IDs start at `len(real_profiles)` (offset computed from in-memory list)
3. `merged = real_profiles + synthetic_profiles`
4. Single `save_profiles(merged)` call writes the final platform file, replacing any interim realtime-written file from Step 1

---

## Out of Scope

- UI for editing the preset company library (file-based config only)
- Per-delegate stance editing in the UI
- Saving/reusing a generated delegate roster across simulations
