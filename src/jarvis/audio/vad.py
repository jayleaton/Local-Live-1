from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

try:
    import webrtcvad
except ImportError as e:  # pragma: no cover
    raise ImportError("voice support requires the 'voice' extra: uv sync --extra voice") from e


class VadSegmenter:
    """End-of-utterance segmentation from a stream of 16 kHz mono int16 frames.

    Tuned for conversational barge-in: a short pre-roll captures the start of
    speech, `start_frames` consecutive voiced frames are required before we
    commit (kills single-frame clicks), and `end_silence_ms` of trailing silence
    closes the utterance.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        aggressiveness: int = 2,
        start_frames: int = 3,
        end_silence_ms: int = 700,
        pre_roll_ms: int = 300,
        max_speech_s: float = 30.0,
    ) -> None:
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("sample_rate must be 8/16/32/48 kHz for WebRTC VAD")
        if frame_ms not in (10, 20, 30):
            raise ValueError("frame_ms must be 10, 20 or 30")
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._vad = webrtcvad.Vad(aggressiveness)
        self._start_frames = start_frames
        self._end_frames = max(1, int(end_silence_ms / frame_ms))
        self._max_frames = int(max_speech_s * 1000 / frame_ms)
        self._preroll: deque[np.ndarray] = deque(maxlen=max(1, int(pre_roll_ms / frame_ms)))
        self._buf: list[np.ndarray] = []
        self._voiced = 0
        self._silence = 0
        self.active = False
        self.just_started = False

    def _reset(self) -> None:
        self._buf = []
        self._voiced = 0
        self._silence = 0
        self.active = False

    def push(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Feed one int16 frame; return a complete utterance when it ends."""
        self.just_started = False
        if frame.dtype != np.int16:
            frame = frame.astype(np.int16)
        if len(frame) * 2 != self.frame_bytes:
            # pad/truncate to the expected frame size
            frame = frame[: self.frame_bytes // 2]
            if len(frame) * 2 < self.frame_bytes:
                frame = np.pad(frame, (0, self.frame_bytes // 2 - len(frame)))
        is_speech = self._vad.is_speech(frame.tobytes(), self.sample_rate)

        if not self.active:
            self._preroll.append(frame)
            if is_speech:
                self._voiced += 1
                if self._voiced >= self._start_frames:
                    self.active = True
                    self.just_started = True
                    self._buf = list(self._preroll)
                    self._preroll.clear()
                    self._silence = 0
            else:
                self._voiced = 0
            return None

        self._buf.append(frame)
        self._silence = 0 if is_speech else self._silence + 1
        if self._silence >= self._end_frames or len(self._buf) >= self._max_frames:
            utterance = np.concatenate(self._buf) if self._buf else None
            self._reset()
            return utterance
        return None
