"""Memory backend dispatcher — tools service.
Selects Zep Cloud or Graphiti implementation based on Config.MEMORY_BACKEND.
"""
from ..config import Config

if Config.MEMORY_BACKEND == 'zep':
    from ._backends.zep.tools import (  # noqa: F401
        ZepToolsService, SearchResult, NodeInfo, EdgeInfo,
        InsightForgeResult, PanoramaResult, AgentInterview, InterviewResult,
    )
else:
    from ._backends.graphiti.tools import (  # noqa: F401
        ZepToolsService, SearchResult, NodeInfo, EdgeInfo,
        InsightForgeResult, PanoramaResult, AgentInterview, InterviewResult,
    )

__all__ = [
    'ZepToolsService', 'SearchResult', 'NodeInfo', 'EdgeInfo',
    'InsightForgeResult', 'PanoramaResult', 'AgentInterview', 'InterviewResult',
]
