from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Role
    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    @staticmethod
    def system(content: str) -> "Message":
        return Message(role="system", content=content)

    @staticmethod
    def user(content: str) -> "Message":
        return Message(role="user", content=content)

    @staticmethod
    def assistant(content: Optional[str] = None, tool_calls: Optional[list[ToolCall]] = None) -> "Message":
        return Message(role="assistant", content=content, tool_calls=list(tool_calls or []))

    @staticmethod
    def tool(tool_call_id: str, name: str, content: str) -> "Message":
        return Message(role="tool", tool_call_id=tool_call_id, name=name, content=content)


@dataclass(frozen=True)
class ToolSpec:
    """A namespaced tool exposed to the model."""

    name: str  # namespaced: "<server>.<tool>"
    server: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[dict[str, Any]] = None
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    raw_name: str = ""


@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: str = ""
    structured: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    untrusted: bool = True
    duration_ms: float = 0.0


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


@dataclass
class AuditEntry:
    ts: float
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)
