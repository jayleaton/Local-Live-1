from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from jarvis.mcp.manager import MCPClientManager, ServerConfig

ROOT = Path(__file__).resolve().parents[1]
SERVER = str(ROOT / "servers" / "demo_mcp_server.py")


def _run(coro):
    return asyncio.run(coro)


async def _happy_path():
    mgr = MCPClientManager([ServerConfig(name="demo", command=[sys.executable, SERVER])])
    await mgr.start()
    try:
        names = {t.name for t in mgr.tools()}
        assert {"demo.add", "demo.now", "demo.save_note", "demo.delete_note"} <= names

        add = await mgr.call("demo.add", {"a": 2, "b": 40})
        assert add.ok and "42" in add.content

        err = await mgr.call("demo.divide", {"a": 1, "b": 0})
        assert not err.ok and "zero" in (err.error or "").lower()

        note = await mgr.call("demo.save_note", {"text": "buy milk"})
        assert note.ok and "note 1" in note.content

        deleted = await mgr.call("demo.delete_note", {"id": "1"})
        assert deleted.ok

        ghost = await mgr.call("demo.nope", {})
        assert not ghost.ok and "unknown" in (ghost.error or "").lower()
    finally:
        await mgr.stop()


async def _bad_server():
    mgr = MCPClientManager([ServerConfig(name="bad", command=["definitely-not-a-real-command-xyz"])])
    await mgr.start()
    assert "bad" in mgr.errors
    assert mgr.tools() == []


def test_mcp_stdio_end_to_end():
    _run(_happy_path())


def test_mcp_bad_server_is_isolated():
    _run(_bad_server())
