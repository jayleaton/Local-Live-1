from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from jarvis.models import ensure_kokoro
from jarvis.tts.base import TTS


class KokoroTTS(TTS):
    """Local streaming TTS via kokoro-onnx (82M params, Apache-2.0)."""

    sample_rate = 24000

    def __init__(
        self,
        *,
        voice: str = "af_heart",
        speed: float = 1.0,
        model_path: Optional[Path] = None,
        voices_path: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        on_progress=None,
        language: str = "en-us",
    ) -> None:
        self.voice = voice
        self.speed = speed
        self.language = language
        if model_path and voices_path:
            self._model_path, self._voices_path = Path(model_path), Path(voices_path)
        else:
            self._model_path, self._voices_path = ensure_kokoro(cache_dir, on_progress)
        self._kokoro = None

    def _load(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
        return self._kokoro

    def synthesize(self, text: str, *, voice: str | None = None, speed: float = 1.0) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        kokoro = self._load()
        samples, _sr = kokoro.create(
            text,
            voice=voice or self.voice,
            speed=speed or self.speed,
            lang=self.language,
        )
        return np.asarray(samples, dtype=np.float32)
