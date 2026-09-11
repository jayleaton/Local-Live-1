from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from jarvis.stt.base import STT


def _to_float32(audio: np.ndarray) -> np.ndarray:
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    if audio.dtype != np.float32:
        return audio.astype(np.float32)
    return audio


def resample_to_16k(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Resample mono float32 audio to 16 kHz using ffmpeg (via faster-whisper's av)."""
    if sample_rate == 16000:
        return audio
    from faster_whisper.audio import decode_audio

    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    buf.seek(0)
    return np.asarray(decode_audio(buf, sampling_rate=16000), dtype=np.float32)


class FasterWhisperSTT(STT):
    """Local CPU STT via faster-whisper / CTranslate2 (no torch)."""

    def __init__(
        self,
        model_size: str = "base.en",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        download_root: Optional[Path] = None,
        beam_size: int = 1,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.download_root = str(download_root) if download_root else None
        self.beam_size = beam_size
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        audio = _to_float32(audio)
        audio = resample_to_16k(audio, sample_rate)
        model = self._load()
        segments, _info = model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
