from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from jarvis.stt.base import STT
    from jarvis.stt.whisper_local import FasterWhisperSTT

# Heavy/optional backends (numpy, faster-whisper, sherpa-onnx) must not load just
# because something imports the package. The core must stay importable with no
# optional dependencies installed.
_LAZY = {
    "STT": ("jarvis.stt.base", "STT"),
    "FasterWhisperSTT": ("jarvis.stt.whisper_local", "FasterWhisperSTT"),
    "SherpaStreamingSTT": ("jarvis.stt.sherpa_streaming", "SherpaStreamingSTT"),
}

__all__ = ["STT", "FasterWhisperSTT", "SherpaStreamingSTT"]


def __getattr__(name: str):
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        import importlib

        return getattr(importlib.import_module(module_name), attr)
    import importlib

    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from e
