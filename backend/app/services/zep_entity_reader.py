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
