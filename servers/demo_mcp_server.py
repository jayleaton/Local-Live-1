#!/usr/bin/env python3
"""A tiny MCP stdio server used to exercise the Jarvis harness end to end.

Implements just enough of the protocol: initialize, tools/list, tools/call,
ping. stdout carries JSON-RPC only; diagnostics go to stderr.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Callable

PROTOCOL_VERSION = "2026-07-28"
_notes: dict[str, str] = {}
_next_note = [1]


def _tool(name: str, description: str, schema: dict, annotations: dict | None = None) -> dict:
    t = {"name": name, "description": description, "inputSchema": schema}
    if annotations:
        t["annotations"] = annotations
    return t


TOOLS = [
    _tool(
        "add",
        "Add two integers.",
        {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]},
        {"readOnlyHint": True, "idempotentHint": True},
    ),
    _tool("now", "Current local time as HH:MM:SS.", {"type": "object", "properties": {}}, {"readOnlyHint": True}),
    _tool(
        "divide",
        "Divide a by b. Fails loudly on divide-by-zero (for error-path testing).",
        {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
        {"readOnlyHint": True},
    ),
    _tool(
        "save_note",
        "Save a note and return its id.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        {"readOnlyHint": False, "idempotentHint": False},
    ),
    _tool(
        "delete_note",
        "Delete a saved note by id. Destructive.",
        {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        {"readOnlyHint": False, "destructiveHint": True},
    ),
]


def _text(content: str, *, is_error: bool = False, structured: dict | None = None) -> dict:
    out: dict[str, Any] = {"content": [{"type": "text", "text": content}]}
    if is_error:
        out["isError"] = True
    if structured is not None:
        out["structuredContent"] = structured
    return out


def handle_add(args: dict) -> dict:
    total = int(args["a"]) + int(args["b"])
    return _text(f"{args['a']} + {args['b']} = {total}", structured={"result": total})


def handle_now(args: dict) -> dict:
    return _text(time.strftime("%H:%M:%S"))


def handle_divide(args: dict) -> dict:
    b = float(args["b"])
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return _text(str(float(args["a"]) / b))


def handle_save_note(args: dict) -> dict:
    note_id = str(_next_note[0])
    _next_note[0] += 1
    _notes[note_id] = str(args["text"])
    return _text(f"saved note {note_id}", structured={"id": note_id})


def handle_delete_note(args: dict) -> dict:
    note_id = str(args["id"])
    if note_id not in _notes:
        return _text(f"no such note: {note_id}", is_error=True)
    del _notes[note_id]
    return _text(f"deleted note {note_id}")


HANDLERS: dict[str, Callable[[dict], dict]] = {
    "add": handle_add,
    "now": handle_now,
    "divide": handle_divide,
    "save_note": handle_save_note,
    "delete_note": handle_delete_note,
}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def respond(rid: Any, result: dict) -> None:
    send({"jsonrpc": "2.0", "id": rid, "result": result})


def error(rid: Any, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def dispatch(msg: dict) -> None:
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        respond(
            rid,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "jarvis-demo", "version": "0.0.1"},
            },
        )
    elif method == "notifications/initialized" or method == "notifications/cancelled":
        return
    elif method == "ping":
        respond(rid, {})
    elif method == "tools/list":
        respond(rid, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            error(rid, -32602, f"unknown tool: {name}")
            return
        try:
            respond(rid, handler(args))
        except Exception as e:  # noqa: BLE001
            respond(rid, _text(f"{type(e).__name__}: {e}", is_error=True))
    elif rid is not None:
        error(rid, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(f"bad json: {line[:120]}", file=sys.stderr)
            continue
        try:
            dispatch(msg)
        except Exception as e:  # noqa: BLE001
            print(f"dispatch error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
