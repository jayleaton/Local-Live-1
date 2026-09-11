"""Managed llama.cpp runtime for local GGUF models.

Non-Apple-Silicon machines can't use MLX, so on-device inference uses
``llama-server`` from the llama.cpp nightly releases. This module downloads a
platform/GPU-appropriate build, locates ``llama-server``, and runs it with GPU
offload (``-ngl 999``), exposing an OpenAI-compatible endpoint the harness uses.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

REPO = "ggml-org/llama.cpp"
CACHE = Path(os.environ.get("JARVIS_LLAMA_DIR", Path.home() / ".cache" / "jarvis" / "llama.cpp"))
FALLBACK_TAG = "b10809"


def _arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def gpu_backend() -> str:
    """Best available llama.cpp backend for this machine."""
    if os.name == "nt":
        if shutil.which("nvidia-smi"):
            return "cuda"
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        if (system32 / "vulkan-1.dll").exists():
            return "vulkan"
        return "cpu"
    if sys.platform == "darwin":
        return "metal"
    if Path("/usr/lib/x86_64-linux-gnu/libvulkan.so.1").exists() or shutil.which("vulkaninfo"):
        return "vulkan"
    return "cpu"


def _release_tag() -> str:
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/latest", headers={"User-Agent": "jarvis/0.0.1"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())  # noqa: S310
        for asset in data.get("assets", []):
            if asset.get("name") == "nightly-tag.txt":
                return urllib.request.urlopen(asset["browser_download_url"], timeout=15).read().decode().strip()  # noqa: S310
        return data.get("tag_name", FALLBACK_TAG)
    except Exception:  # noqa: BLE001
        return FALLBACK_TAG


def _asset(tag: str, backend: str) -> Optional[str]:
    arch = _arch()
    if os.name == "nt":
        suffix = {"cuda": "cuda-12.4", "vulkan": "vulkan", "cpu": "cpu"}.get(backend, "cpu")
        return f"llama-{tag}-bin-win-{suffix}-{arch}.zip"
    if sys.platform == "darwin":
        return f"llama-{tag}-bin-macos-{arch}.tar.gz"
    suffix = "vulkan" if backend == "vulkan" else "x64"
    return f"llama-{tag}-bin-ubuntu-{suffix}-x64.tar.gz"


def _download(url: str, dest: Path, on_progress: Optional[Callable[[str], None]] = None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis/0.0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0) or 0)
        got = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress and total:
                on_progress(f"downloading llama.cpp {int(100 * got / total)}%")


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            try:
                t.extractall(dest, filter="data")
            except TypeError:  # pragma: no cover
                t.extractall(dest)


def _find_server(root: Path) -> Optional[Path]:
    names = ("llama-server.exe", "llama-server")
    for name in names:
        for p in root.rglob(name):
            if p.is_file():
                return p
    return None


def find_server(backend: Optional[str] = None) -> Optional[Path]:
    env = os.environ.get("LLAMA_SERVER_BIN")
    if env and Path(env).exists():
        return Path(env)
    if CACHE.exists():
        if backend:
            for d in CACHE.glob(f"*-{backend}"):
                found = _find_server(d)
                if found:
                    return found
        else:
            # Prefer a GPU build over CPU when several are installed.
            gpu_dirs = sorted(
                (d for d in CACHE.iterdir() if d.is_dir() and d.name.rsplit("-", 1)[-1] not in ("cpu",)),
                key=lambda d: d.name,
                reverse=True,
            )
            for d in gpu_dirs + [d for d in CACHE.iterdir() if d.is_dir()]:
                found = _find_server(d)
                if found:
                    return found
    which = shutil.which("llama-server")
    return Path(which) if which else None


def install(backend: Optional[str] = None, on_progress: Optional[Callable[[str], None]] = None, timeout: float = 1800.0) -> Path:
    """Download and extract llama.cpp, returning the llama-server path."""
    backend = backend or gpu_backend()
    existing = find_server(backend)
    if existing:
        return existing
    tag = _release_tag()
    asset = _asset(tag, backend)
    if not asset:
        raise RuntimeError(f"no llama.cpp build for {sys.platform}/{_arch()}")
    work = Path(tempfile.mkdtemp(prefix="jarvis-llama-"))
    try:
        url = f"https://github.com/{REPO}/releases/download/{tag}/{asset}"
        archive = work / asset
        if on_progress:
            on_progress(f"downloading {asset}")
        _download(url, archive, on_progress)
        dest = CACHE / f"{tag}-{backend}"
        _extract(archive, dest)
        if os.name == "nt" and backend == "cuda":
            cudart = f"cudart-llama-bin-win-cuda-12.4-{_arch()}.zip"
            try:
                cu = work / cudart
                _download(f"https://github.com/{REPO}/releases/download/{tag}/{cudart}", cu, on_progress)
                _extract(cu, dest)
            except Exception:  # noqa: BLE001 - optional runtime DLLs
                pass
        server = _find_server(dest)
        if not server:
            raise RuntimeError(f"llama-server not found in {dest}")
        if on_progress:
            on_progress(f"installed llama.cpp ({backend})")
        return server
    finally:
        shutil.rmtree(work, ignore_errors=True)


def start(model_path: str, port: int, *, ctx: int = 8192, n_gpu_layers: int = 999, wait: float = 180.0) -> subprocess.Popen:
    server = find_server()
    if not server:
        server = install()
    cmd = [
        str(server),
        "-m", str(model_path),
        "-ngl", str(n_gpu_layers),
        "-c", str(ctx),
        "--host", "127.0.0.1",
        "--port", str(port),
    ]
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **kwargs)
    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("llama-server exited during startup")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:  # noqa: S310
                if r.status == 200:
                    return proc
        except Exception:  # noqa: BLE001
            time.sleep(1.0)
    proc.terminate()
    raise RuntimeError("llama-server did not become ready")


def stop(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.terminate()
    except Exception:  # noqa: BLE001
        pass
