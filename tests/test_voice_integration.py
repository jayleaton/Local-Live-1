"""Real-model voice integration. Skipped unless JARVIS_VOICE_IT=1 (downloads models)."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("JARVIS_VOICE_IT") != "1", reason="set JARVIS_VOICE_IT=1 to run model downloads"
)

pytest.importorskip("sounddevice")
pytest.importorskip("faster_whisper")
pytest.importorskip("kokoro_onnx")


def test_tts_stt_round_trip():
    from jarvis.stt.whisper_local import FasterWhisperSTT
    from jarvis.tts.kokoro_tts import KokoroTTS

    tts = KokoroTTS(voice="af_sarah")
    audio = tts.synthesize("The quick brown fox jumps over the lazy dog.")
    text = FasterWhisperSTT("base.en").transcribe(audio, tts.sample_rate)
    assert "quick brown fox" in text.lower()
    assert "lazy dog" in text.lower()
