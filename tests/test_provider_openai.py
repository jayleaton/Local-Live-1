from __future__ import annotations

import asyncio
import json

from jarvis.core.types import Message, ToolSpec
from jarvis.llm.openai_compat import (
    OpenAICompatProvider,
    build_tool_name_map,
    messages_to_openai,
    sanitize_tool_name,
    tools_to_openai,
)


def _spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, server=name.split(".")[0], raw_name=name.split(".")[-1], description="d")


def test_sanitize_tool_name_allows_only_safe_chars():
    assert sanitize_tool_name("demo.add") == "demo_add"
    assert sanitize_tool_name("fs.read/file") == "fs_read_file"
    assert sanitize_tool_name("") == "tool"


def test_name_map_is_deterministic_and_collision_free():
    tools = [_spec("demo.add"), _spec("demo-add")]
    mapping = build_tool_name_map(tools)
    assert len(set(mapping.values())) == 2
    assert mapping == build_tool_name_map(tools)


def test_messages_encode_assistant_tool_names():
    from jarvis.core.types import ToolCall

    msg = Message.assistant(None, [ToolCall(id="1", name="demo.add", arguments={"a": 1})])
    encoded = messages_to_openai([msg], {"demo.add": "demo_add"})
    assert encoded[0]["tool_calls"][0]["function"]["name"] == "demo_add"


def test_deepseek_payload_and_name_decoding():
    provider = OpenAICompatProvider(
        "https://api.deepseek.com",
        "deepseek-flash",
        extra_params={"thinking": {"type": "disabled"}},
        reasoning_effort="low",
    )
    captured: dict = {}

    def fake_post(payload: dict, cancel):
        captured.update(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "demo_add", "arguments": json.dumps({"a": 2, "b": 40})}}
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "model": "deepseek-flash",
        }

    provider._post = fake_post  # type: ignore[assignment]
    resp = asyncio.run(provider.complete([Message.user("add")], [_spec("demo.add")]))

    assert captured["thinking"] == {"type": "disabled"}
    assert captured["reasoning_effort"] == "low"
    assert captured["tools"][0]["function"]["name"] == "demo_add"
    # provider-safe name decoded back to the internal namespaced name
    assert resp.tool_calls[0].name == "demo.add"
    assert resp.tool_calls[0].arguments == {"a": 2, "b": 40}


def test_tools_strict_flag():
    payload = tools_to_openai([_spec("demo.add")], {}, strict=True)
    assert payload[0]["function"]["strict"] is True
