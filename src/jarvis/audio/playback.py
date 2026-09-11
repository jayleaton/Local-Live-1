from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError as e:  # pragma: no cover
    raise ImportError("voice support requires the 'voice' extra: uv sync --extra voice") from e

from jarvis.core.events import CancelToken


class Speaker:
    """Blocking, cancelable playback of mono float32 audio."""

    def __init__(self, *, device: Optional[int] = None, block_ms: int = 50) -> None:
        self.device = device
        self.block_ms = block_ms

    def play(
        self,
        audio: np.ndarray,
        sample_rate: int,
        *,
        cancel: Optional[CancelToken] = None,
    ) -> bool:
        """Play audio. Returns True if it finished, False if cancelled."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.reshape(-1)
        block = max(1, int(sample_rate * self.block_ms / 1000))
        with sd.OutputStream(
            samplerate=sample_rate, channels=1, dtype="float32", device=self.device
        ) as stream:
            for i in range(0, len(audio), block):
                if cancel and cancel.cancelled:
                    return False
                stream.write(audio[i : i + block])
        return True
