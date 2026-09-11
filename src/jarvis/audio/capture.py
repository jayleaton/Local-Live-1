from __future__ import annotations

from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError as e:  # pragma: no cover
    raise ImportError("voice support requires the 'voice' extra: uv sync --extra voice") from e


class Microphone:
    """16 kHz mono int16 capture. The callback fires on PortAudio's thread."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        device: Optional[int] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.blocksize = int(sample_rate * frame_ms / 1000)
        self.device = device
        self._stream: Optional[sd.InputStream] = None

    def start(self, on_frame: Callable[[np.ndarray], None]) -> None:
        def _cb(indata, frames, time_info, status) -> None:  # noqa: ANN001
            on_frame(indata[:, 0].copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            channels=1,
            dtype="int16",
            device=self.device,
            callback=_cb,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None


def list_devices() -> str:
    return str(sd.query_devices())
