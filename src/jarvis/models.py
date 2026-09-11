from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_CACHE = Path(os.environ.get("JARVIS_MODEL_DIR", Path.home() / ".cache" / "jarvis" / "models"))

KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def _download(url: str, dest: Path, on_progress: Callable[[str, int, int], None] | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 - trusted model host
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(dest.name, got, total)
    tmp.replace(dest)


def ensure_kokoro(
    cache_dir: Path | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Download the Kokoro TTS ONNX model + voices if not already cached."""
    cache = cache_dir or DEFAULT_CACHE / "kokoro"
    paths = []
    for name, url in KOKORO_FILES.items():
        dest = cache / name
        if not dest.exists():
            _download(url, dest, on_progress)
        paths.append(dest)
    return paths[0], paths[1]
