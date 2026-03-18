# Memory Backend Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `MEMORY_BACKEND=graphiti|zep` env var that switches the memory implementation at startup, with both backends fully functional.

**Architecture:** Extract the current Graphiti implementations and restored Zep implementations into `services/_backends/graphiti/` and `services/_backends/zep/`. The existing top-level service files (`zep_entity_reader.py`, etc.) become 3-line dispatchers that import from the correct backend based on `Config.MEMORY_BACKEND`. No callers change.

**Tech Stack:** Python, `graphiti-core>=0.3`, `zep-cloud==3.13.0`, Flask

---

## File Map

**Create:**
- `backend/app/services/_backends/__init__.py` — empty, makes it a package
- `backend/app/services/_backends/graphiti/__init__.py` — empty
- `backend/app/services/_backends/zep/__init__.py` — empty
- `backend/app/services/_backends/graphiti/entity_reader.py` — Graphiti entity reader
- `backend/app/services/_backends/graphiti/memory_updater.py` — Graphiti memory updater
- `backend/app/services/_backends/graphiti/tools.py` — Graphiti tools
- `backend/app/services/_backends/graphiti/graph_builder.py` — Graphiti graph builder
- `backend/app/services/_backends/graphiti/oasis_profile.py` — Graphiti OASIS profile generator
- `backend/app/services/_backends/zep/zep_paging.py` — Zep pagination (restored)
- `backend/app/services/_backends/zep/entity_reader.py` — Zep entity reader (restored)
- `backend/app/services/_backends/zep/memory_updater.py` — Zep memory updater (restored)
- `backend/app/services/_backends/zep/tools.py` — Zep tools (restored)
- `backend/app/services/_backends/zep/graph_builder.py` — Zep graph builder (restored)
- `backend/app/services/_backends/zep/oasis_profile.py` — Zep OASIS profile generator (restored)

**Modify:**
- `backend/app/config.py` — add `MEMORY_BACKEND`, `ZEP_API_KEY`, update `validate()`
- `backend/pyproject.toml` — restore `zep-cloud==3.13.0`
- `backend/app/services/zep_entity_reader.py` — replace with dispatcher
- `backend/app/services/zep_graph_memory_updater.py` — replace with dispatcher
- `backend/app/services/zep_tools.py` — replace with dispatcher
- `backend/app/services/graph_builder.py` — replace with dispatcher
- `backend/app/services/oasis_profile_generator.py` — replace with dispatcher
- `.env.example` — document `MEMORY_BACKEND` and `ZEP_API_KEY`
- `README.md` — document both backends

---

## Import path reference

The `_backends/` directory is 3 levels deep inside `app/`:
`app/services/_backends/graphiti/entity_reader.py`

From that depth, relative imports are:
- `.` = current package (`app.services._backends.graphiti`)
- `..` = `app.services._backends`
- `...` = `app.services`
- `....` = `app`

So `from ....config import Config` reaches `app.config`, and `from ...graphiti_client import GraphitiClientFactory` reaches `app.services.graphiti_client`.

---

## Task 1: Config and dependencies

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add `MEMORY_BACKEND` and `ZEP_API_KEY` to `config.py`**

In `backend/app/config.py`, after the `GRAPHITI_EMBED_API_KEY` line (currently line 46), add:

```python
    # Memory backend selection
    MEMORY_BACKEND = os.environ.get('MEMORY_BACKEND', 'graphiti')  # 'graphiti' or 'zep'
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
```

- [ ] **Step 2: Update `Config.validate()` to be backend-aware**

Replace the current `validate()` body (lines 79–88) with:

```python
    @classmethod
    def validate(cls):
        """Validate required configuration, basically check if critical API keys are set or not."""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        if cls.MEMORY_BACKEND == 'zep':
            if not cls.ZEP_API_KEY:
                errors.append("ZEP_API_KEY is not configured (required when MEMORY_BACKEND=zep)")
        else:
            if not cls.NEO4J_URI:
                errors.append("NEO4J_URI is not configured")
            if not cls.NEO4J_PASSWORD:
                errors.append("NEO4J_PASSWORD is not configured")
            if not cls.GRAPHITI_EMBED_BASE_URL:
                errors.append("GRAPHITI_EMBED_BASE_URL is not configured")
        return errors
```

- [ ] **Step 3: Restore `zep-cloud==3.13.0` in `pyproject.toml`**

In `backend/pyproject.toml`, find the `dependencies` list and add `"zep-cloud==3.13.0"` alongside `"graphiti-core>=0.3"`:

```toml
    "graphiti-core>=0.3",
    "zep-cloud==3.13.0",
```

- [ ] **Step 4: Update `.env.example`**

After the existing Graphiti section, add:

```bash
# Memory backend selection
# Set to 'zep' to use Zep Cloud instead of Graphiti (default: graphiti)
MEMORY_BACKEND=graphiti

# Zep Cloud API key (required when MEMORY_BACKEND=zep)
# ZEP_API_KEY=your_zep_api_key
```

- [ ] **Step 5: Update README.md**

In the "Quick Start" env block in `README.md`, add after the Neo4j/Graphiti block:

```
# Optional: switch to Zep Cloud instead of Graphiti
# MEMORY_BACKEND=zep
# ZEP_API_KEY=your_zep_api_key
```

- [ ] **Step 6: Run `uv sync` to install `zep-cloud`**

```bash
cd backend && uv sync
```

Expected: resolves successfully, installs `zep-cloud==3.13.0`.

- [ ] **Step 7: Verify config loads**

```bash
cd backend && python -c "
from app.config import Config
print('MEMORY_BACKEND:', Config.MEMORY_BACKEND)
print('ZEP_API_KEY present:', bool(Config.ZEP_API_KEY))
errors = Config.validate()
print('Validate errors:', errors)
"
```

Expected: `MEMORY_BACKEND: graphiti`, no errors (assuming `.env.local` has Neo4j vars).

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/pyproject.toml .env.example README.md backend/uv.lock
git commit -m "feat: add MEMORY_BACKEND config, restore zep-cloud dependency"
```

---

## Task 2: Create `_backends/` package skeleton

**Files:**
- Create: `backend/app/services/_backends/__init__.py`
- Create: `backend/app/services/_backends/graphiti/__init__.py`
- Create: `backend/app/services/_backends/zep/__init__.py`

- [ ] **Step 1: Create the three `__init__.py` files** (all empty)

```bash
mkdir -p backend/app/services/_backends/graphiti
mkdir -p backend/app/services/_backends/zep
touch backend/app/services/_backends/__init__.py
touch backend/app/services/_backends/graphiti/__init__.py
touch backend/app/services/_backends/zep/__init__.py
```

- [ ] **Step 2: Verify Python can import the packages**

```bash
cd backend && python -c "import app.services._backends.graphiti; import app.services._backends.zep; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/_backends/
git commit -m "feat: add _backends package skeleton"
```

---

## Task 3: Create Graphiti backend files

Move the current Graphiti implementations from the top-level service files into `_backends/graphiti/`. The only changes are import paths — all logic is identical.

**Import rule:** Every `from ..X` in the original becomes `from ....X` in the backend file (two extra dots). Every `from .X` (sibling service) becomes `from ...X` (up to `app.services`) or `from .X` if it's within the same backend package.

**Files:**
- Create: `backend/app/services/_backends/graphiti/entity_reader.py`
- Create: `backend/app/services/_backends/graphiti/memory_updater.py`
- Create: `backend/app/services/_backends/graphiti/tools.py`
- Create: `backend/app/services/_backends/graphiti/graph_builder.py`
- Create: `backend/app/services/_backends/graphiti/oasis_profile.py`

- [ ] **Step 1: Create `entity_reader.py`**

Copy `backend/app/services/zep_entity_reader.py` to `backend/app/services/_backends/graphiti/entity_reader.py`.

Then apply these import substitutions (only the import block at the top changes):

```python
# Replace this import block:
from ..utils.logger import get_logger
from ..utils.graphiti_cypher import (
    fetch_all_nodes,
    fetch_all_edges,
    get_node_by_uuid,
    get_edges_for_node,
)
from .graphiti_client import GraphitiClientFactory

# With this:
from ....utils.logger import get_logger
from ....utils.graphiti_cypher import (
    fetch_all_nodes,
    fetch_all_edges,
    get_node_by_uuid,
    get_edges_for_node,
)
from ...graphiti_client import GraphitiClientFactory
```

- [ ] **Step 2: Create `memory_updater.py`**

Copy `backend/app/services/zep_graph_memory_updater.py` to `backend/app/services/_backends/graphiti/memory_updater.py`.

Apply import substitutions:

```python
# Replace:
from ..utils.logger import get_logger
from .graphiti_client import GraphitiClientFactory

# With:
from ....utils.logger import get_logger
from ...graphiti_client import GraphitiClientFactory
```

(`from graphiti_core.nodes import EpisodeType` is a third-party import — leave it unchanged.)

- [ ] **Step 3: Create `tools.py`**

Copy `backend/app/services/zep_tools.py` to `backend/app/services/_backends/graphiti/tools.py`.

Apply import substitutions:

```python
# Replace:
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from .graphiti_client import GraphitiClientFactory
from ..utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, get_node_by_uuid, get_edges_for_node

# With:
from ....utils.logger import get_logger
from ....utils.llm_client import LLMClient
from ...graphiti_client import GraphitiClientFactory
from ....utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, get_node_by_uuid, get_edges_for_node
```

- [ ] **Step 4: Create `graph_builder.py`**

Copy `backend/app/services/graph_builder.py` to `backend/app/services/_backends/graphiti/graph_builder.py`.

Apply import substitutions:

```python
# Replace:
from ..utils.logger import get_logger
from ..utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, delete_group
from ..models.task import TaskManager, TaskStatus
from .graphiti_client import GraphitiClientFactory
from .text_processor import TextProcessor

# With:
from ....utils.logger import get_logger
from ....utils.graphiti_cypher import fetch_all_nodes, fetch_all_edges, delete_group
from ....models.task import TaskManager, TaskStatus
from ...graphiti_client import GraphitiClientFactory
from ...text_processor import TextProcessor
```

(`from graphiti_core.nodes import EpisodeType` — leave unchanged.)

- [ ] **Step 5: Create `oasis_profile.py`**

Copy `backend/app/services/oasis_profile_generator.py` to `backend/app/services/_backends/graphiti/oasis_profile.py`.

Apply import substitutions:

```python
# Replace:
from ..config import Config
from ..utils.logger import get_logger, log_llm_interaction
from .zep_entity_reader import EntityNode, ZepEntityReader
from .graphiti_client import GraphitiClientFactory

# With:
from ....config import Config
from ....utils.logger import get_logger, log_llm_interaction
from .entity_reader import EntityNode, ZepEntityReader
from ...graphiti_client import GraphitiClientFactory
```

- [ ] **Step 6: Verify imports work**

```bash
cd backend && python -c "
from app.services._backends.graphiti.entity_reader import ZepEntityReader, EntityNode, FilteredEntities
from app.services._backends.graphiti.memory_updater import ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity
from app.services._backends.graphiti.tools import ZepToolsService
from app.services._backends.graphiti.graph_builder import GraphBuilderService
from app.services._backends.graphiti.oasis_profile import OasisProfileGenerator, OasisAgentProfile
print('All Graphiti backend imports OK')
"
```

Expected: `All Graphiti backend imports OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/_backends/graphiti/
git commit -m "feat: add Graphiti backend files to _backends/graphiti/"
```

---

## Task 4: Create Zep backend files

Restore the original Zep implementations from git commit `bc65fea^` (the commit immediately before the Graphiti migration began), then fix the import paths for the new location.

**Files:**
- Create: `backend/app/services/_backends/zep/zep_paging.py`
- Create: `backend/app/services/_backends/zep/entity_reader.py`
- Create: `backend/app/services/_backends/zep/memory_updater.py`
- Create: `backend/app/services/_backends/zep/tools.py`
- Create: `backend/app/services/_backends/zep/graph_builder.py`
- Create: `backend/app/services/_backends/zep/oasis_profile.py`

- [ ] **Step 1: Export Zep files from git**

```bash
git show bc65fea^:backend/app/utils/zep_paging.py > backend/app/services/_backends/zep/zep_paging.py
git show bc65fea^:backend/app/services/zep_entity_reader.py > backend/app/services/_backends/zep/entity_reader.py
git show bc65fea^:backend/app/services/zep_graph_memory_updater.py > backend/app/services/_backends/zep/memory_updater.py
git show bc65fea^:backend/app/services/zep_tools.py > backend/app/services/_backends/zep/tools.py
git show bc65fea^:backend/app/services/graph_builder.py > backend/app/services/_backends/zep/graph_builder.py
git show bc65fea^:backend/app/services/oasis_profile_generator.py > backend/app/services/_backends/zep/oasis_profile.py
```

- [ ] **Step 2: Fix imports in `zep_paging.py`**

The original file (from `app/utils/`) has exactly one relative import — the logger. There is no `Config` import. Replace:

```python
from .logger import get_logger
```

With:
```python
from ....utils.logger import get_logger
```

All other imports (`from zep_cloud import ...`) are third-party and stay unchanged.

- [ ] **Step 3: Fix imports in `entity_reader.py`**

Original:
```python
from zep_cloud.client import Zep
from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
```

Replace with:
```python
from zep_cloud.client import Zep
from ....config import Config
from ....utils.logger import get_logger
from .zep_paging import fetch_all_nodes, fetch_all_edges
```

- [ ] **Step 4: Fix imports in `memory_updater.py`**

Original:
```python
from zep_cloud.client import Zep
from ..config import Config
from ..utils.logger import get_logger
```

Replace with:
```python
from zep_cloud.client import Zep
from ....config import Config
from ....utils.logger import get_logger
```

- [ ] **Step 5: Fix imports in `tools.py`**

Original:
```python
from zep_cloud.client import Zep
from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
```

Replace with:
```python
from zep_cloud.client import Zep
from ....config import Config
from ....utils.logger import get_logger
from ....utils.llm_client import LLMClient
from .zep_paging import fetch_all_nodes, fetch_all_edges
```

- [ ] **Step 6: Fix imports in `graph_builder.py`**

Original:
```python
from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget
from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor
```

Replace with:
```python
from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget
from ....config import Config
from ....models.task import TaskManager, TaskStatus
from .zep_paging import fetch_all_nodes, fetch_all_edges
from ...text_processor import TextProcessor
```

- [ ] **Step 7: Fix imports in `oasis_profile.py`**

Original:
```python
from openai import OpenAI
from zep_cloud.client import Zep
from ..config import Config
from ..utils.logger import get_logger, log_llm_interaction
from .zep_entity_reader import EntityNode, ZepEntityReader
```

Replace with:
```python
from openai import OpenAI
from zep_cloud.client import Zep
from ....config import Config
from ....utils.logger import get_logger, log_llm_interaction
from .entity_reader import EntityNode, ZepEntityReader
```

- [ ] **Step 8: Verify Zep backend imports**

```bash
cd backend && python -c "
from app.services._backends.zep.entity_reader import ZepEntityReader, EntityNode, FilteredEntities
from app.services._backends.zep.memory_updater import ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity
from app.services._backends.zep.tools import ZepToolsService
from app.services._backends.zep.graph_builder import GraphBuilderService
from app.services._backends.zep.oasis_profile import OasisProfileGenerator, OasisAgentProfile
print('All Zep backend imports OK')
"
```

Expected: `All Zep backend imports OK`

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/_backends/zep/
git commit -m "feat: add Zep backend files to _backends/zep/ (restored from pre-migration)"
```

---

## Task 5: Convert service files to dispatchers

Replace the contents of all 5 top-level service files with thin dispatcher code. The dispatchers read `Config.MEMORY_BACKEND` at import time and re-export the right backend's classes.

**Files:**
- Modify: `backend/app/services/zep_entity_reader.py`
- Modify: `backend/app/services/zep_graph_memory_updater.py`
- Modify: `backend/app/services/zep_tools.py`
- Modify: `backend/app/services/graph_builder.py`
- Modify: `backend/app/services/oasis_profile_generator.py`

- [ ] **Step 1: Replace `zep_entity_reader.py`**

Overwrite the entire file with:

```python
"""Memory backend dispatcher — entity reader.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.entity_reader import (  # noqa: F401
        ZepEntityReader, EntityNode, FilteredEntities,
    )
else:
    from ._backends.graphiti.entity_reader import (  # noqa: F401
        ZepEntityReader, EntityNode, FilteredEntities,
    )

__all__ = ['ZepEntityReader', 'EntityNode', 'FilteredEntities']
```

- [ ] **Step 2: Replace `zep_graph_memory_updater.py`**

```python
"""Memory backend dispatcher — graph memory updater.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.memory_updater import (  # noqa: F401
        ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity,
    )
else:
    from ._backends.graphiti.memory_updater import (  # noqa: F401
        ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity,
    )

__all__ = ['ZepGraphMemoryUpdater', 'ZepGraphMemoryManager', 'AgentActivity']
```

- [ ] **Step 3: Replace `zep_tools.py`**

```python
"""Memory backend dispatcher — tools service.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.tools import (  # noqa: F401
        ZepToolsService, SearchResult, NodeInfo, EdgeInfo, InsightForgeResult,
    )
else:
    from ._backends.graphiti.tools import (  # noqa: F401
        ZepToolsService, SearchResult, NodeInfo, EdgeInfo, InsightForgeResult,
    )

__all__ = ['ZepToolsService', 'SearchResult', 'NodeInfo', 'EdgeInfo', 'InsightForgeResult']
```

- [ ] **Step 4: Replace `graph_builder.py`**

```python
"""Memory backend dispatcher — graph builder.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.graph_builder import GraphBuilderService, GraphInfo  # noqa: F401
else:
    from ._backends.graphiti.graph_builder import GraphBuilderService, GraphInfo  # noqa: F401

__all__ = ['GraphBuilderService', 'GraphInfo']
```

- [ ] **Step 5: Replace `oasis_profile_generator.py`**

```python
"""Memory backend dispatcher — OASIS profile generator.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.oasis_profile import OasisProfileGenerator, OasisAgentProfile  # noqa: F401
else:
    from ._backends.graphiti.oasis_profile import OasisProfileGenerator, OasisAgentProfile  # noqa: F401

__all__ = ['OasisProfileGenerator', 'OasisAgentProfile']
```

- [ ] **Step 6: Verify dispatchers work (Graphiti default)**

```bash
cd backend && python -c "
from app.services.zep_entity_reader import ZepEntityReader, EntityNode, FilteredEntities
from app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity
from app.services.zep_tools import ZepToolsService
from app.services.graph_builder import GraphBuilderService
from app.services.oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
print('Dispatcher imports OK (Graphiti backend)')
"
```

Expected: `Dispatcher imports OK (Graphiti backend)`

- [ ] **Step 7: Verify dispatchers work (Zep backend)**

```bash
cd backend && MEMORY_BACKEND=zep python -c "
from app.services.zep_entity_reader import ZepEntityReader, EntityNode, FilteredEntities
from app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity
from app.services.zep_tools import ZepToolsService
from app.services.graph_builder import GraphBuilderService
from app.services.oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
print('Dispatcher imports OK (Zep backend)')
"
```

Expected: `Dispatcher imports OK (Zep backend)`

- [ ] **Step 8: Run existing tests**

```bash
cd /Users/henrik/vsc_projects/MiroFish-EN && python -m pytest backend/tests/ -q --ignore=backend/tests/test_simulation_config_delegate.py --ignore=backend/tests/test_synthetic_delegate_generator.py
```

Expected: Same results as before this task (no new failures introduced).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/zep_entity_reader.py \
        backend/app/services/zep_graph_memory_updater.py \
        backend/app/services/zep_tools.py \
        backend/app/services/graph_builder.py \
        backend/app/services/oasis_profile_generator.py
git commit -m "feat: convert service files to backend dispatchers"
```
