from __future__ import annotations

from jarvis.core.types import ToolCall, ToolSpec
from jarvis.policy.gate import PolicyGate


def _spec(name="demo.tool", *, read_only=True, destructive=False):
    return ToolSpec(name=name, server="demo", raw_name=name.split(".")[-1], description="", read_only=read_only, destructive=destructive)


def _call(name="demo.tool"):
    return ToolCall(id="c", name=name)


def test_read_only_allowed_without_confirmation():
    gate = PolicyGate()
    d = gate.check(_call(), _spec(read_only=True))
    assert d.allowed and not d.requires_confirmation


def test_write_requires_confirmation_by_default():
    gate = PolicyGate()
    d = gate.check(_call(), _spec(read_only=False))
    assert d.allowed and d.requires_confirmation


def test_no_confirmer_denies_write():
    import asyncio

    gate = PolicyGate(confirmer=None)
    d = asyncio.run(gate.authorize(_call(), _spec(read_only=False)))
    assert not d.allowed


def test_confirmer_allows_write():
    import asyncio

    gate = PolicyGate(confirmer=lambda c, s: True)
    d = asyncio.run(gate.authorize(_call(), _spec(read_only=False)))
    assert d.allowed


def test_deny_pattern_blocks():
    gate = PolicyGate(auto_approve=True, deny_patterns=["demo.write*"])
    d = gate.check(_call("demo.write_file"), _spec("demo.write_file", read_only=False))
    assert not d.allowed


def test_read_only_only_blocks_write():
    gate = PolicyGate(auto_approve=True, read_only_only=True)
    d = gate.check(_call(), _spec(read_only=False))
    assert not d.allowed


def test_server_allowlist():
    gate = PolicyGate(allowed_servers=["other"])
    d = gate.check(_call(), _spec())
    assert not d.allowed


def test_unknown_tool_denied():
    gate = PolicyGate(auto_approve=True)
    d = gate.check(_call("ghost"), None)
    assert not d.allowed
