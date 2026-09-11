from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterator

import numpy as np

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_PREFIX = re.compile(r"^\s*(#{1,6}\s*|[-*+]\s+|\d+[.)]\s+)", re.MULTILINE)


def to_speech_text(text: str) -> str:
    """Strip anything that should not be read aloud (code, markdown, paths)."""
    if not text:
        return ""
    text = _CODE_BLOCK.sub(" I've prepared the code. ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_PREFIX.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("*", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", ". ", text)
    return text.strip()


def split_sentences(text: str, *, max_chars: int = 200) -> list[str]:
    """Split text into speakable chunks so TTS can start before the full reply is ready."""
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]
    out: list[str] = []
    for part in parts:
        while len(part) > max_chars:
            cut = part.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out


class TTS(ABC):
    sample_rate: int = 24000

    @abstractmethod
    def synthesize(self, text: str, *, voice: str | None = None, speed: float = 1.0) -> np.ndarray:
        raise NotImplementedError

    def synthesize_stream(
        self, text: str, *, voice: str | None = None, speed: float = 1.0
    ) -> Iterator[np.ndarray]:
        """Yield audio per sentence so playback overlaps generation."""
        for sentence in split_sentences(text):
            yield self.synthesize(sentence, voice=voice, speed=speed)
