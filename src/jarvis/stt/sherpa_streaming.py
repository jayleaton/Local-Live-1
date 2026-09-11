from __future__ import annotations

import importlib
import os
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

MODEL_NAME = "sherpa-onnx-streaming-zipformer-en-2023-06-26"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MODEL_NAME}.tar.bz2"
)
DEFAULT_CACHE = Path(os.environ.get("JARVIS_MODEL_DIR", Path.home() / ".cache" / "jarvis" / "models"))


def _ensure_sherpa_runtime() -> None:
    """Make sherpa_onnx load its onnxruntime dylib.

    The macOS wheel looks for libonnxruntime.dylib next to _sherpa_onnx.so; the
    onnxruntime Python package ships it elsewhere. Symlink it if missing.
    """
    try:
        importlib.import_module("sherpa_onnx")
        return
    except ImportError as e:
        if "libonnxruntime" not in str(e):
            raise
    import site

    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    for root in roots:
        sp = Path(root)
        sherpa_lib = sp / "sherpa_onnx" / "lib"
        if not sherpa_lib.exists():
            continue
        candidates = list((sp / "onnxruntime").rglob("libonnxruntime*.dylib"))
        if candidates and not (sherpa_lib / "libonnxruntime.dylib").exists():
            try:
                (sherpa_lib / "libonnxruntime.dylib").symlink_to(os.path.relpath(candidates[0], sherpa_lib))
            except OSError:
                pass
    importlib.invalidate_caches()
    importlib.import_module("sherpa_onnx")


def ensure_model(cache_dir: Optional[Path] = None, on_progress=None) -> Path:
    cache = (cache_dir or DEFAULT_CACHE / "sherpa") / MODEL_NAME
    if (cache / "tokens.txt").exists():
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    archive = cache.parent / f"{MODEL_NAME}.tar.bz2"
    with urllib.request.urlopen(MODEL_URL) as resp, open(archive, "wb") as f:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(MODEL_NAME, got, total)
    with tarfile.open(archive, "r:bz2") as tar:
        tar.extractall(cache.parent)  # noqa: S202 - trusted model host
    archive.unlink(missing_ok=True)
    return cache


def _pick(model_dir: Path, candidates: list[str]) -> str:
    for name in candidates:
        p = model_dir / name
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"none of {candidates} in {model_dir}")


class SherpaStreamingSTT:
    """True streaming (causal) STT with built-in endpointing, on CPU via ONNX.

    Feeds non-overlapping 16 kHz frames and returns partial text incrementally;
    `is_endpoint` signals end-of-utterance so the agent can respond without the
    user pressing anything.
    """

    sample_rate = 16000

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        *,
        num_threads: int = 2,
        enable_endpoint: bool = True,
        trailing_silence: float = 0.8,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir else None
        self.num_threads = num_threads
        self.enable_endpoint = enable_endpoint
        self.trailing_silence = trailing_silence
        self._recognizer = None
        self._buffer = np.zeros(0, dtype=np.float32)

    def _load(self):
        if self._recognizer is not None:
            return self._recognizer
        _ensure_sherpa_runtime()
        import sherpa_onnx

        model_dir = self.model_dir or ensure_model()
        encoder = _pick(model_dir, ["encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx", "encoder-epoch-99-avg-1-chunk-16-left-128.onnx"])
        decoder = _pick(model_dir, ["decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx", "decoder-epoch-99-avg-1-chunk-16-left-128.onnx"])
        joiner = _pick(model_dir, ["joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx", "joiner-epoch-99-avg-1-chunk-16-left-128.onnx"])
        tokens = str(model_dir / "tokens.txt")
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            num_threads=self.num_threads,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            enable_endpoint_detection=self.enable_endpoint,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=self.trailing_silence,
            rule3_min_utterance_length=20,
        )
        return self._recognizer

    def create_stream(self):
        return self._load().create_stream()

    def accept(self, stream, pcm16: np.ndarray) -> None:
        samples = pcm16.astype(np.float32) / 32768.0 if pcm16.dtype == np.int16 else pcm16.astype(np.float32)
        stream.accept_waveform(self.sample_rate, samples)
        rec = self._load()
        while rec.is_ready(stream):
            rec.decode_stream(stream)

    def text(self, stream) -> str:
        return self._load().get_result(stream)

    def is_endpoint(self, stream) -> bool:
        rec = self._load()
        return bool(rec.is_endpoint(stream))

    def reset(self, stream) -> None:
        self._load().reset(stream)
