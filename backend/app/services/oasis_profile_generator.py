"""Memory backend dispatcher — OASIS profile generator.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.oasis_profile import OasisProfileGenerator, OasisAgentProfile  # noqa: F401
else:
    from ._backends.graphiti.oasis_profile import OasisProfileGenerator, OasisAgentProfile  # noqa: F401

__all__ = ['OasisProfileGenerator', 'OasisAgentProfile']
