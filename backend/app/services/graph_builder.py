"""Memory backend dispatcher — graph builder.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.graph_builder import GraphBuilderService, GraphInfo  # noqa: F401
else:
    from ._backends.graphiti.graph_builder import GraphBuilderService, GraphInfo  # noqa: F401

__all__ = ['GraphBuilderService', 'GraphInfo']
