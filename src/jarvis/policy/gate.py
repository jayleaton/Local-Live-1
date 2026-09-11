from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from jarvis.core.types import ToolCall, ToolSpec

Confirmer = Callable[[ToolCall, ToolSpec], Awaitable[bool] | bool]

# Tools whose names look like writes/mutations are treated as side-effecting even
# if the server did not annotate them. Conservative default for an always-on agent.
MUTATING_PATTERNS = [
    "*write*",
    "*create*",
    "*delete*",
    "*remove*",
    "*update*",
    "*edit*",
    "*move*",
    "*rename*",
    "*save*",
    "*set*",
    "*exec*",
    "*shell*",
    "*run*",
    "*post*",
    "*send*",
    "*purchase*",
    "*pay*",
    "*transfer*",
]


@dataclass
class PolicyDecision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""

    @property
    def denied(self) -> bool:
        return not self.allowed


class PolicyGate:
    """Default-deny permission gate for tool execution.

    - Optional server allowlist (empty = all configured servers allowed).
    - Deny patterns/match by namespaced tool name.
    - Anything side-effecting requires explicit confirmation.
    - `read_only_only` blocks all non-read-only tools outright (useful mode).
    """

    def __init__(
        self,
        *,
        allowed_servers: Optional[list[str]] = None,
        deny_patterns: Optional[list[str]] = None,
        confirm_patterns: Optional[list[str]] = None,
        read_only_only: bool = False,
        auto_approve: bool = False,
        confirmer: Optional[Confirmer] = None,
    ) -> None:
        self.allowed_servers = set(allowed_servers) if allowed_servers else None
        self.deny_patterns = list(deny_patterns if deny_patterns is not None else [])
        self.confirm_patterns = list(confirm_patterns or []) + MUTATING_PATTERNS
        self.read_only_only = read_only_only
        self.auto_approve = auto_approve
        self.confirmer = confirmer

    def check(self, call: ToolCall, spec: Optional[ToolSpec]) -> PolicyDecision:
        name = call.name
        if spec is None:
            return PolicyDecision(False, reason=f"unknown tool: {name}")
        if self.allowed_servers is not None and spec.server not in self.allowed_servers:
            return PolicyDecision(False, reason=f"server not allowed: {spec.server}")
        if any(fnmatch.fnmatch(name, p) for p in self.deny_patterns):
            return PolicyDecision(False, reason=f"matched deny pattern: {name}")
        if self.read_only_only and not spec.read_only:
            return PolicyDecision(False, reason=f"read-only mode: {name} is not read-only")
        if self.auto_approve:
            return PolicyDecision(True, reason="auto-approved")
        side_effecting = spec.destructive or (not spec.read_only)
        if side_effecting:
            return PolicyDecision(True, requires_confirmation=True, reason=f"side-effecting: {name}")
        if any(fnmatch.fnmatch(name, p) for p in self.confirm_patterns):
            return PolicyDecision(True, requires_confirmation=True, reason=f"matched confirm pattern: {name}")
        return PolicyDecision(True, reason="read-only")

    async def authorize(self, call: ToolCall, spec: Optional[ToolSpec]) -> PolicyDecision:
        decision = self.check(call, spec)
        if not decision.allowed or not decision.requires_confirmation:
            return decision
        if self.confirmer is None:
            return PolicyDecision(False, reason=f"confirmation required but no confirmer: {call.name}")
        ok = self.confirmer(call, spec)  # type: ignore[arg-type]
        if hasattr(ok, "__await__"):
            ok = await ok  # type: ignore[misc]
        if ok:
            return PolicyDecision(True, reason="user approved")
        return PolicyDecision(False, reason="user denied")


def make_allowlist_gate(servers: list[str], **kw) -> PolicyGate:
    return PolicyGate(allowed_servers=servers, **kw)
