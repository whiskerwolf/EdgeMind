"""
EdgeMind Multi-Step AI Agent Package.

Provides autonomous multi-turn reasoning and native tool-calling capabilities
for static code analysis, constraint parsing, coverage gap evaluation,
and edge-case synthesis.
"""

from core.agents.orchestrator import AgentOrchestrator
from core.agents.provider import (
    BaseAgentProvider,
    LiveAgentProvider,
    MockAgentProvider,
    OllamaAgentProvider,
    ThinkTagFilter,
)
from core.agents.schemas import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentMessage,
    AgentState,
    AgentStatus,
    AgentStepResult,
    ToolCall,
    ToolExecutionRecord,
    ToolExecutionStatus,
)
from core.agents.tools import (
    RegisteredTool,
    ToolRegistry,
    default_tool_registry,
)

__all__ = [
    "AgentOrchestrator",
    "BaseAgentProvider",
    "MockAgentProvider",
    "LiveAgentProvider",
    "OllamaAgentProvider",
    "ThinkTagFilter",
    "ToolRegistry",
    "RegisteredTool",
    "default_tool_registry",
    "AgentAnalyzeRequest",
    "AgentAnalyzeResponse",
    "AgentMessage",
    "AgentState",
    "AgentStatus",
    "AgentStepResult",
    "ToolCall",
    "ToolExecutionRecord",
    "ToolExecutionStatus",
]
