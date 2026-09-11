from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class STT(ABC):
    sample_rate: int = 16000

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe mono audio (float32 or int16) and return text."""
        raise NotImplementedError
