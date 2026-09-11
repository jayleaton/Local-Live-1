"""Model catalog + installer wrapper around the NeMo-Speech.cpp CLI.

The CLI (``nemo-speech``) already owns the hard parts: an indexed catalog
(``--json model list``), verified/resumable downloads (``pull``), and a
per-platform installer script. This module exposes just enough of that to let
the app show the user which speech model is active, choose another, and have it
downloaded in the background — the same workflow as NVIDIA's playground.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from jarvis.stt.nemotron_server import find_binary

INSTALL_SH_URL = "https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.sh"
INSTALL_PS1_URL = "https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.ps1"

# Only these ASR models accept the realtime/streaming path the app uses.
STREAMING_ASR_REPOS = {
    "nvidia/nemotron-3.5-asr-streaming-0.6b",
    "nvidia/nemotron-speech-streaming-en-0.6b",
}

_LABELS = {
    "nemotron-3.5-asr-streaming-0.6b": "Nemotron 3.5 ASR Streaming 0.6B",
    "nemotron-speech-streaming-en-0.6b": "Nemotron Speech Streaming EN 0.6B",
    "parakeet-tdt-0.6b-v3": "Parakeet TDT 0.6B v3 (offline)",
    "parakeet-ctc-1.1b": "Parakeet CTC 1.1B (offline)",
}

# `model list --json` reports roles/aliases but not artifact sizes; keep the
# published sizes so the UI can show a download estimate.
_KNOWN_SIZES = {
    "nvidia/nemotron-3.5-asr-streaming-0.6b": 741_548_352,
    "nvidia/nemotron-speech-streaming-en-0.6b": 699_872_960,
    "nvidia/parakeet-ctc-1.1b": 1_178_100_960,
    "nvidia/parakeet-tdt-0.6b-v3": 713_975_456,
}


def cache_dir(platform: Optional[str] = None, env: Optional[dict] = None) -> Path:
    """Where ``nemo-speech`` stores downloaded models (see its install docs)."""
    platform = platform or ("windows" if os.name == "nt" else sys.platform)
    env = os.environ if env is None else env
    override = env.get("NEMO_SPEECH_MODEL_DIR")
    if override:
        return Path(override)
    if platform.startswith("win") or platform == "windows":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NeMoSpeech" / "models"
    if platform == "darwin":
        return Path.home() / "Library" / "Caches" / "NeMoSpeech" / "models"
    xdg = env.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "nemo-speech" / "models"


def is_downloaded(filename: str, size: int = 0, root: Optional[Path] = None) -> bool:
    if not filename:
        return False
    base = cache_dir() if root is None else Path(root)
    if not base.exists():
        return False
    target = Path(filename).name
    for path in base.rglob(target):
        try:
            if path.is_file() and (size <= 0 or path.stat().st_size >= size):
                return True
        except OSError:  # pragma: no cover - transient FS access error
            continue
    return False


def _label(repo: str) -> str:
    name = repo.split("/")[-1]
    return _LABELS.get(name, name)


def _iter_index_models(data: dict) -> Iterator[dict]:
    """Accept the documented ``{models:[...]}`` shape and category maps alike."""
    if isinstance(data.get("models"), list):
        yield from data["models"]
        return
    for value in data.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
        elif isinstance(value, dict) and value.get("repo"):
            yield value


def _as_list(value) -> list:
    if isinstance(value, str):
        return [value]
    return list(value or [])


def _is_asr(model: dict) -> bool:
    if "asr" in _as_list(model.get("roles")) or "asr" in _as_list(model.get("default_for")):
        return True
    # index.json shape (used by tests and any older catalog)
    return any((a or {}).get("role") == "asr" for a in (model.get("artifacts") or []))


def _matches(rel: str, repo: str) -> bool:
    """Match a cache-relative path against a repo, any revision.

    The cache layout is ``<owner>/<name>/<revision>/<file>``; matching the
    owner/name path means any already-installed revision counts as installed,
    so the UI never offers a second copy of the same model.
    """
    rel = rel.replace("\\", "/")
    if repo and "/" in repo:
        return repo in rel
    name = repo.split("/")[-1]
    return bool(name) and name in rel


def is_installed(repo: str, size: int = 0, root: Optional[Path] = None) -> bool:
    """True only when a complete copy exists (any revision).

    A partial download also leaves files, so when the published size is known we
    require the on-disk bytes to reach it; that keeps "installed" honest and
    still lets `pull` resume an interrupted download.
    """
    base = cache_dir() if root is None else Path(root)
    if not repo or not base.exists():
        return False
    total = 0
    for path in base.rglob("*"):
        try:
            if path.is_file() and _matches(str(path.relative_to(base)), repo):
                total += path.stat().st_size
        except OSError:  # pragma: no cover
            continue
    if total == 0:
        return False
    expected = size or _KNOWN_SIZES.get(repo, 0)
    if expected:
        return total >= int(expected * 0.99)
    return True


def _cached(repo: str, root: Optional[Path] = None) -> bool:
    return is_installed(repo, root=root)


def cached_bytes(repo: str, root: Optional[Path] = None) -> int:
    """Bytes of this repo already present in the cache (for a progress bar)."""
    base = cache_dir() if root is None else Path(root)
    if not repo or not base.exists():
        return 0
    total = 0
    for path in base.rglob("*"):
        try:
            if path.is_file() and _matches(str(path.relative_to(base)), repo):
                total += path.stat().st_size
        except OSError:  # pragma: no cover
            continue
    return total


def _entry(model: dict, root: Optional[Path] = None) -> Optional[dict]:
    repo = model.get("repo") or model.get("id") or ""
    if not repo or not _is_asr(model):
        return None
    artifacts = [a for a in (model.get("artifacts") or []) if a.get("role") == "asr"]
    filename = (artifacts[0].get("filename") or "") if artifacts else ""
    size = int(artifacts[0].get("size") or 0) if artifacts else _KNOWN_SIZES.get(repo, 0)
    aliases = [a for a in (model.get("aliases") or []) if isinstance(a, str)]
    downloaded = is_downloaded(filename, size, root=root) if filename else is_installed(repo, size, root=root)
    return {
        "repo": repo,
        "name": aliases[0] if aliases else repo,
        "aliases": aliases,
        "label": _label(repo),
        "filename": filename,
        "size": size,
        "size_mb": round(size / 1e6, 1) if size else None,
        "downloaded": downloaded,
        "installed": downloaded,
        "streaming": repo in STREAMING_ASR_REPOS,
        "license": model.get("license") or "",
    }


def list_models(timeout: float = 30.0) -> dict:
    """Catalog of ASR models from the installed CLI, or an empty/installed=False result."""
    binary = find_binary()
    if not binary:
        return {"runtime_installed": False, "cli_path": None, "models": []}
    try:
        proc = subprocess.run(
            [binary, "--json", "model", "list"],
            capture_output=True,
            text=True,
            timeout=timeout,
            **_no_window(),
        )
        data = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else {}
    except Exception:  # noqa: BLE001 - a broken catalog must not break Settings
        data = {}
    models = [e for e in (_entry(m) for m in _iter_index_models(data)) if e]
    default_repo = (data.get("defaults") or {}).get("asr") if isinstance(data, dict) else None
    return {"runtime_installed": True, "cli_path": binary, "models": models, "default": default_repo}


def _no_window() -> dict:
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def _stream(cmd: list[str], on_progress: Optional[Callable[[str], None]], timeout: Optional[float] = None) -> None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **_no_window(),
    )
    assert proc.stdout is not None
    # curl-style progress uses bare carriage returns; split on both so the bar
    # can advance without waiting for a newline that may never come.
    buf = ""
    while True:
        ch = proc.stdout.read(1)
        if ch == "":
            break
        if ch in ("\r", "\n"):
            line = buf.strip()
            if line and on_progress:
                on_progress(line)
            buf = ""
        else:
            buf += ch
    if buf.strip() and on_progress:
        on_progress(buf.strip())
    proc.wait(timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed (exit {proc.returncode})")


def pull(name: str, on_progress: Optional[Callable[[str], None]] = None, timeout: float = 3600.0) -> None:
    """Download (or verify/resume) one indexed model ahead of time."""
    binary = find_binary()
    if not binary:
        raise RuntimeError("nemo-speech is not installed")
    _stream([binary, "pull", name], on_progress, timeout=timeout)


def _fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis/0.0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:  # noqa: S310
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def install_runtime(on_progress: Optional[Callable[[str], None]] = None, timeout: float = 3600.0) -> None:
    """Run NVIDIA's official installer to place ``nemo-speech`` on this machine."""
    if find_binary():
        if on_progress:
            on_progress("nemo-speech already installed")
        return
    workdir = Path(tempfile.mkdtemp(prefix="nemo-speech-install-"))
    if os.name == "nt":
        script = workdir / "install.ps1"
        _fetch(INSTALL_PS1_URL, script)
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = workdir / "install.sh"
        _fetch(INSTALL_SH_URL, script)
        cmd = ["/bin/sh", str(script)]
    if on_progress:
        on_progress("running NVIDIA installer…")
    _stream(cmd, on_progress, timeout=timeout)
    if find_binary() is None:
        raise RuntimeError("installer finished but nemo-speech was not found")


_PERCENT = re.compile(r"(\d{1,3})\s*%")


def parse_percent(line: str) -> Optional[int]:
    match = _PERCENT.search(line)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))
