# ADR-0001: Deepen Backend Modules — Unify LLM, Split Report, Extract Prep Orchestration

**Date**: 2026-06-03  
**Status**: Accepted  
**Deciders**: @Polypod

## Context

The backend had accumulated architectural friction:

1. **Three independent LLM adapters** — `SimulationConfigGenerator`, `SyntheticDelegateGenerator`, and `LLMClient` each constructed their own `OpenAI()` client with separate retry, JSON repair, and fence-stripping logic. Bugs had to be fixed in 3 places.

2. **`report_agent.py` was ~2600 lines** — mixing prompt templates (400 lines), file persistence (`ReportManager`), and the ReACT orchestration loop. Untestable without running the full LLM + filesystem stack.

3. **`api/simulation.py` contained ~100-line orchestration closures** — the `/prepare` endpoint defined a background task with progress callback translation that belonged in the service layer.

## Decision

### 1. Single deep `LLMClient`

Added `chat_json_with_retry()` to `utils/llm_client.py` absorbing:
- Retry with configurable attempts
- Temperature decay per retry
- Truncated-JSON repair (brace/bracket closing)
- Markdown fence stripping
- `<think>` tag removal

`SimulationConfigGenerator` and `SyntheticDelegateGenerator` now accept an injected `LLMClient` and delegate all LLM interaction to it.

### 2. Three-module report split

| Module | Lines | Role |
|--------|-------|------|
| `report_prompts.py` | 414 | Prompt template constants |
| `report_manager.py` | 632 | Persistence, progress, CRUD, data models |
| `report_agent.py` | 781 | ReACT loop, tool dispatch, chat |

### 3. Service-layer prep orchestration

Added to `SimulationManager`:
- `check_prepared()` — moved from API route's `_check_simulation_prepared()`
- `run_prepare_task()` — encapsulates progress callback translation + task lifecycle

The API route is now a thin dispatcher: validate → dispatch → respond.

## Consequences

**Positive:**
- LLM policy changes (new model quirks, retry tuning) are single-file fixes
- ReportAgent's ReACT loop is testable with a mock `LLMClient` + mock `ReportManager`
- The prepare endpoint can't accidentally diverge from service-layer state management
- 39/39 tests pass with updated mocks

**Negative / risks:**
- `SyntheticEntityNode` still duck-types `EntityNode` with no shared Protocol — drift risk remains (candidate for future ADR)
- `SimulationRunner` still uses class-level mutable state — not addressed here

## Not Decided (explicitly deferred)

- **EntityNode Protocol** — defining a `typing.Protocol` would formalize the seam. Deferred because it's low-risk today (only 2 implementations) and requires choosing where the protocol lives.
- **SimulationRunner registry** — converting class-level dicts to injectable instance. Deferred because it's a larger refactor touching process management.
- **Deleting `TextProcessor`** — trivial pass-through, but low priority.
