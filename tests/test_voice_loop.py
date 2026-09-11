from __future__ import annotations

import asyncio
import time

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sounddevice")

from jarvis.core.types import LLMResponse
from jarvis.harness.loop import AgentHarness  # noqa: E402
from jarvis.llm.scripted import ScriptedProvider  # noqa: E402
from jarvis.policy.gate import PolicyGate  # noqa: E402
from jarvis.runtime.memory import InMemoryToolRuntime  # noqa: E402
from jarvis.tts.base import split_sentences  # noqa: E402
from jarvis.voice.loop import VoiceConfig, VoiceLoop  # noqa: E402


class FakeSTT:
    sample_rate = 16000

    def __init__(self, text="hello jarvis"):
        self.text = text

    def transcribe(self, audio, sample_rate=16000):
        return self.text


class FakeSpeaker:
    sample_rate = 24000

    def __init__(self, delay=0.005):
        self.played = 0
        self.delay = delay

    def play(self, audio, sample_rate, cancel=None):
        if cancel and cancel.cancelled:
            return False
        time.sleep(self.delay)
        self.played += 1
        return not (cancel and cancel.cancelled)


class FakeTTS:
    sample_rate = 24000

    def __init__(self, chunks=40):
        self.chunks = chunks

    def synthesize_stream(self, text, voice=None, speed=1.0):
        for _ in range(self.chunks):
            yield np.ones(2400, dtype=np.float32) * 0.01


def _harness(reply="Hi there."):
    runtime = InMemoryToolRuntime()
    provider = ScriptedProvider(lambda messages, tools: LLMResponse(text=reply))
    return AgentHarness(provider, runtime, PolicyGate(auto_approve=True))


def test_split_sentences():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences("") == []


def test_to_speech_text_strips_code_and_markdown():
    from jarvis.tts.base import to_speech_text

    out = to_speech_text("Here you go:\n```python\nprint('hi')\n```\n**Done** — see [docs](http://example.com/x)")
    assert "print" not in out
    assert "```" not in out
    assert "http" not in out
    assert "Done" in out


def test_respond_speaks_reply():
    logs: list[str] = []
    loop = VoiceLoop(_harness("Hi there."), FakeSTT(), FakeTTS(3), speaker=FakeSpeaker(), log=logs.append)
    asyncio.run(loop._respond("hello"))
    assert any(l.startswith("jarvis>") for l in logs)


def test_barge_in_stops_playback_early():
    async def flow():
        speaker = FakeSpeaker(delay=0.01)
        loop = VoiceLoop(_harness("Sure, let me tell you a long story."), FakeSTT(), FakeTTS(60), speaker=speaker, log=lambda m: None)
        task = asyncio.create_task(loop._respond("tell me a story"))
        await asyncio.sleep(0.05)  # let a few chunks play
        assert loop._active_cancel is not None
        loop._active_cancel.cancel()  # simulate barge-in
        await task
        return speaker.played

    played = asyncio.run(flow())
    assert played < 60, "barge-in must stop TTS playback early"
    assert played >= 1


def test_request_stop_cancels_active_turn():
    async def flow():
        loop = VoiceLoop(_harness("long reply"), FakeSTT(), FakeTTS(60), speaker=FakeSpeaker(delay=0.01), log=lambda m: None)
        task = asyncio.create_task(loop._respond("hi"))
        await asyncio.sleep(0.03)
        loop.request_stop()
        await task
        return loop._stop.is_set()

    assert asyncio.run(flow()) is True


def test_handle_utterance_transcribes_and_responds():
    logs: list[str] = []
    loop = VoiceLoop(_harness("pong"), FakeSTT("ping"), FakeTTS(2), speaker=FakeSpeaker(), log=logs.append)
    asyncio.run(loop._handle_utterance(np.zeros(16000, dtype=np.int16)))
    assert any("you> ping" in l for l in logs)
    assert any("jarvis> pong" in l for l in logs)
