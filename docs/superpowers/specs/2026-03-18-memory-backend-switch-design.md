# Spec: Pluggable Memory Backend (Graphiti / Zep Cloud)

**Date:** 2026-03-18
**Status:** Approved

---

## Background

The Graphiti migration (`2026-03-18-graphiti-memory-migration-design.md`) replaced all Zep Cloud internals with Graphiti equivalents while preserving the existing service filenames and exported class names. This spec adds a runtime switch so either backend can be selected via an environment variable, with both fully functional.

---

## Scope

### What changes

| Area | Change |
| --- | --- |
| `services/_backends/graphiti/` | New directory — receives the Graphiti internals extracted from current service files |
| `services/_backends/zep/` | New directory — receives the original Zep Cloud implementations restored from git |
| `services/zep_entity_reader.py` | Becomes a thin dispatcher (3 lines) |
| `services/zep_graph_memory_updater.py` | Becomes a thin dispatcher |
| `services/zep_tools.py` | Becomes a thin dispatcher |
| `services/graph_builder.py` | Becomes a thin dispatcher |
| `services/oasis_profile_generator.py` | Becomes a thin dispatcher |
| `app/config.py` | Add `MEMORY_BACKEND`, restore `ZEP_API_KEY`, update `validate()` |
| `backend/pyproject.toml` | Restore `zep-cloud==3.13.0` alongside `graphiti-core` |
| `.env.example` | Document `MEMORY_BACKEND` and `ZEP_API_KEY` |
| `README.md` | Document both backend options |

### What does NOT change

- `services/graphiti_client.py` — unchanged
- `utils/graphiti_cypher.py` — unchanged
- All callers: `simulation_runner.py`, `simulation_manager.py`, `simulation_config_generator.py`, `simulation.py`, `report_agent.py`, `report.py`, `services/__init__.py`
- No frontend changes

---

## Architecture

### Directory layout

```text
backend/app/services/
  _backends/
    __init__.py          (empty)
    graphiti/
      __init__.py        (empty)
      entity_reader.py   ← Graphiti internals from zep_entity_reader.py
      memory_updater.py  ← Graphiti internals from zep_graph_memory_updater.py
      tools.py           ← Graphiti internals from zep_tools.py
      graph_builder.py   ← Graphiti internals from graph_builder.py
      oasis_profile.py   ← Graphiti internals from oasis_profile_generator.py
    zep/
      __init__.py        (empty)
      entity_reader.py   ← Zep internals restored from git (bc65fea^)
      memory_updater.py  ← Zep internals restored from git
      tools.py           ← Zep internals restored from git
      graph_builder.py   ← Zep internals restored from git
      oasis_profile.py   ← Zep internals restored from git
  zep_entity_reader.py   ← dispatcher
  zep_graph_memory_updater.py ← dispatcher
  zep_tools.py           ← dispatcher
  graph_builder.py       ← dispatcher
  oasis_profile_generator.py ← dispatcher
  graphiti_client.py     ← unchanged
```

### Dispatcher pattern

Each top-level service file becomes a one-way import switch:

```python
from app.config import Config

if Config.MEMORY_BACKEND == 'zep':
    from app.services._backends.zep.entity_reader import (
        ZepEntityReader, EntityNode, FilteredEntities,
    )
else:
    from app.services._backends.graphiti.entity_reader import (
        ZepEntityReader, EntityNode, FilteredEntities,
    )

__all__ = ['ZepEntityReader', 'EntityNode', 'FilteredEntities']
```

The `else` branch is the default (Graphiti), so any unrecognised value falls through to Graphiti.

### Backend file contents

**Graphiti backends** — move the current implementation wholesale from the top-level service file into the corresponding `_backends/graphiti/` file. No logic changes.

**Zep backends** — restore from git commit `bc65fea^` (the commit immediately before `bc65fea "feat: swap zep-cloud dependency for graphiti-core, update config"`). The files at that ref are the last clean Zep Cloud implementations before any migration edits.

Files to restore:

- `backend/app/services/zep_entity_reader.py` → `_backends/zep/entity_reader.py`
- `backend/app/services/zep_graph_memory_updater.py` → `_backends/zep/memory_updater.py`
- `backend/app/services/zep_tools.py` → `_backends/zep/tools.py`
- `backend/app/services/graph_builder.py` → `_backends/zep/graph_builder.py`
- `backend/app/services/oasis_profile_generator.py` → `_backends/zep/oasis_profile.py`
- `backend/app/utils/zep_paging.py` → restore alongside Zep backend (it is used by the Zep service files); place at `_backends/zep/zep_paging.py` and update its internal imports

The restored Zep service files (`entity_reader.py`, `tools.py`, `graph_builder.py`) import from `zep_paging` — these imports must be updated to relative paths within `_backends/zep/` (e.g. `from . import zep_paging`).

`zep_paging.py` itself imports `from ..config import Config` for `ZEP_API_KEY`. After being moved one level deeper (to `_backends/zep/`), this relative path must be updated to `from ...config import Config`.

---

## Configuration

### New environment variable

```bash
MEMORY_BACKEND=graphiti   # default; set to 'zep' to use Zep Cloud
```

### Restored environment variable

```bash
ZEP_API_KEY=your_zep_api_key   # required when MEMORY_BACKEND=zep
```

### `Config` class changes

```python
MEMORY_BACKEND: str = os.environ.get('MEMORY_BACKEND', 'graphiti')
ZEP_API_KEY: str | None = os.environ.get('ZEP_API_KEY')
```

### `Config.validate()` changes

```python
if Config.MEMORY_BACKEND == 'zep':
    # check ZEP_API_KEY
else:
    # check NEO4J_URI, NEO4J_PASSWORD, GRAPHITI_EMBED_BASE_URL  (existing)
```

---

## Dependencies

Both packages stay in `pyproject.toml`:

```toml
"graphiti-core>=0.3",
"zep-cloud==3.13.0",
```

Both are always installed. The inactive backend's package is present but its client is never instantiated when not selected.

---

## Error handling

- An unknown `MEMORY_BACKEND` value (not `graphiti`, not `zep`) falls through to Graphiti silently (default `else` branch). No special error needed.
- `validate()` raises the same `ConfigurationError` pattern as existing checks when required vars are missing for the selected backend.

---

## Testing notes

- After the change, start with `MEMORY_BACKEND=graphiti` (default) and confirm existing behaviour is unchanged.
- Set `MEMORY_BACKEND=zep` with a valid `ZEP_API_KEY` and confirm the Zep path loads without import errors.
- No new automated tests are added.
