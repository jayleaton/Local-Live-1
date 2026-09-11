from __future__ import annotations

import importlib
import os
import shutil
import tarfile
import tempfile
import threading
import time
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

# `ensure_model` may run from several WebSocket handler threads at once (the UI
# reconnects while the first download is still going). Serialize it and make the
# on-disk result atomic, so a partial download/extract can never masquerade as a
# usable model.
_download_lock = threading.Lock()

# The recognizer accepts either the int8 or the full-precision files; a complete
# model has tokens plus at least one usable file from each of these groups.
_REQUIRED_GROUPS: tuple[tuple[str, ...], ...] = (
    ("tokens.txt",),
    (
        "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
        "encoder-epoch-99-avg-1-chunk-16-left-128.onnx",
    ),
    (
        "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
        "decoder-epoch-99-avg-1-chunk-16-left-128.onnx",
    ),
    (
        "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
        "joiner-epoch-99-avg-1-chunk-16-left-128.onnx",
    ),
)


def _model_complete(cache: Path) -> bool:
    for group in _REQUIRED_GROUPS:
        if not any((cache / name).is_file() and (cache / name).stat().st_size > 0 for name in group):
            return False
    return True


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    try:
        tar.extractall(dest, filter="data")  # py3.12+
    except TypeError:  # pragma: no cover - older interpreters
        tar.extractall(dest)  # noqa: S202 - trusted model host


def _download(url: str, dest: Path, on_progress=None, retries: int = 3) -> None:
    """Download to `dest` atomically, retrying on truncation/network errors."""
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        part = dest.with_name(dest.name + ".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "jarvis/0.0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as f:  # noqa: S310
                total = int(resp.headers.get("Content-Length", 0) or 0)
                got = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if on_progress:
                        on_progress(MODEL_NAME, got, total)
            if total and got != total:
                raise OSError(f"incomplete download: {got}/{total} bytes")
            os.replace(part, dest)
            return
        except Exception as e:  # noqa: BLE001 - retry any transport error
            last = e
            part.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise OSError(f"failed to download {url}: {last}")


def _preload_onnxruntime() -> None:
    """Load the `onnxruntime` package's DLL before sherpa-onnx asks for it.

    Windows ships an ancient ``C:\\Windows\\System32\\onnxruntime.dll`` that
    shadows the one bundled with the Python package, because a bare-name
    ``LoadLibrary("onnxruntime.dll")`` checks System32 before PATH. ``_sherpa_onnx``
    then fails with "requested API version [28] ... only [1,17] are supported".
    Preloading the package DLL by full path makes the later bare-name load
    resolve to the compatible, already-loaded module. No-op off Windows.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        import onnxruntime

        capi = Path(onnxruntime.__file__).parent / "capi"
        dll = capi / "onnxruntime.dll"
        if not dll.exists():
            return
        try:
            os.add_dll_directory(str(capi))
        except (AttributeError, OSError):
            pass
        ctypes.CDLL(str(dll))
    except Exception:  # noqa: BLE001 - best effort; import will surface real errors
        pass


def _ensure_sherpa_runtime() -> None:
    """Make sherpa_onnx load a compatible onnxruntime shared library.

    On Windows, preload the Python package's DLL (System32 shadows it). On macOS,
    the wheel looks for libonnxruntime.dylib next to _sherpa_onnx.so; the
    onnxruntime Python package ships it elsewhere, so symlink it if missing.
    """
    _preload_onnxruntime()
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
    base = Path(cache_dir) if cache_dir else DEFAULT_CACHE / "sherpa"
    cache = base / MODEL_NAME
    with _download_lock:
        if _model_complete(cache):
            return cache
        # A previous run may have left a partial extraction (this is what produced
        # `EOFError: Compressed file ended before end-of-stream`). Start clean.
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        archive = base / f"{MODEL_NAME}.tar.bz2"
        tmpdir = Path(tempfile.mkdtemp(prefix=f".{MODEL_NAME}-", dir=str(base)))
        _download(MODEL_URL, archive, on_progress)
        try:
            with tarfile.open(archive, "r:bz2") as tar:
                _safe_extract(tar, tmpdir)
            extracted = tmpdir / MODEL_NAME
            src = extracted if extracted.is_dir() else tmpdir
            shutil.move(str(src), str(cache))
            if not _model_complete(cache):
                raise OSError(f"model archive did not contain a complete {MODEL_NAME}")
            return cache
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            archive.unlink(missing_ok=True)


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
