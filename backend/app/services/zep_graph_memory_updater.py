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
