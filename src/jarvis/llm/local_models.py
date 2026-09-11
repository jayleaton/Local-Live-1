"""On-device brain model catalog and downloader.

Apple Silicon uses MLX; everything else uses GGUF via llama.cpp. The catalog is
platform-aware, download status is read from the Hugging Face cache (size-aware,
so partial downloads can resume), and downloads run through the shared model-job
progress reporting.
"""

from __future__ import annotations

import platform
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

MLX_CATALOG = [
    {"repo": "mlx-community/Qwen3.5-4B-MLX-4bit", "file": "", "label": "Qwen3.5 4B (MLX 4-bit)", "runtime": "mlx"},
    {"repo": "mlx-community/Qwen3.5-9B-MLX-4bit", "file": "", "label": "Qwen3.5 9B (MLX 4-bit)", "runtime": "mlx"},
    {"repo": "mlx-community/Qwen2.5-3B-Instruct-4bit", "file": "", "label": "Qwen2.5 3B Instruct (MLX 4-bit)", "runtime": "mlx"},
]

GGUF_CATALOG = [
    {"repo": "unsloth/Qwen3.5-4B-GGUF", "file": "Qwen3.5-4B-Q4_K_M.gguf", "label": "Qwen3.5 4B (fast)", "runtime": "llama.cpp"},
    {"repo": "unsloth/Qwen3.5-9B-GGUF", "file": "Qwen3.5-9B-Q4_K_M.gguf", "label": "Qwen3.5 9B (balanced)", "runtime": "llama.cpp"},
    {
        "repo": "brunopio/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-Q4_K_M-GGUF",
        "file": "qwen3.5-14b-a3b-claude-4.6-opus-reasoning-distilled-reap-q4_k_m.gguf",
        "label": "Qwen3.5 14B-A3B (smarter)",
        "runtime": "llama.cpp",
        # This community GGUF embeds a minimal chat template with no tool support,
        # so we supply the base model's proper tool-aware template.
        "chat_template_url": "https://huggingface.co/tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap/raw/main/chat_template.jinja",
    },
]

_sizes: dict[str, int] = {}
_size_lock = threading.Lock()


def apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64")


def catalog() -> list[dict]:
    return MLX_CATALOG if apple_silicon() else GGUF_CATALOG


def _find(repo: str) -> Optional[dict]:
    for item in MLX_CATALOG + GGUF_CATALOG:
        if item["repo"] == repo:
            return item
    return None


def runtime_for(repo: str, filename: str = "") -> str:
    item = _find(repo)
    return item["runtime"] if item else ("llama.cpp" if filename else "mlx")


def _hub():
    from huggingface_hub import HfApi

    return HfApi()


def file_size(repo: str, filename: str = "") -> int:
    """Bytes of the repo (whole repo for MLX, one file for GGUF); 0 when offline."""
    key = f"{repo}:{filename}"
    with _size_lock:
        if key in _sizes:
            return _sizes[key]
    size = 0
    try:
        info = _hub().model_info(repo, files_metadata=True)
        files = list(info.siblings or [])
        if filename:
            match = next((f for f in files if getattr(f, "rfilename", "") == filename), None)
            size = int(getattr(match, "size", 0) or 0) if match else 0
        else:
            size = sum(int(getattr(f, "size", 0) or 0) for f in files)
    except Exception:  # noqa: BLE001 - offline / gated
        size = 0
    with _size_lock:
        _sizes[key] = size
    return size


def cached_bytes(repo: str, filename: str = "") -> int:
    try:
        if filename:
            from huggingface_hub import try_to_load_from_cache

            path = try_to_load_from_cache(repo_id=repo, filename=filename)
            return Path(path).stat().st_size if isinstance(path, str) and Path(path).exists() else 0
        from huggingface_hub import scan_cache_dir

        total = 0
        for entry in scan_cache_dir().repos:
            if entry.repo_id == repo:
                for rev in entry.revisions:
                    total += int(rev.size_on_disk)
        return total
    except Exception:  # noqa: BLE001
        return 0


def is_downloaded(repo: str, filename: str = "", size: int = 0) -> bool:
    total = cached_bytes(repo, filename)
    if total == 0:
        return False
    expected = size or file_size(repo, filename)
    if expected:
        return total >= int(expected * 0.98)
    return True


def list_models() -> list[dict]:
    out = []
    for item in catalog():
        repo, filename = item["repo"], item["file"]
        size = file_size(repo, filename)
        out.append(
            {
                "repo": repo,
                "name": repo,
                "file": filename,
                "label": item["label"],
                "runtime": item["runtime"],
                "size": size,
                "size_mb": round(size / 1e6, 1) if size else None,
                "downloaded": is_downloaded(repo, filename, size),
            }
        )
    return out


def pull(repo: str, filename: str = "", on_progress: Optional[Callable[[str], None]] = None, token: Optional[str] = None) -> None:
    if on_progress:
        on_progress(f"downloading {filename or repo}")
    if filename:
        from huggingface_hub import hf_hub_download

        hf_hub_download(repo_id=repo, filename=filename, token=token)
    else:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=repo, token=token)
    if on_progress:
        on_progress("done")


def chat_template_path(repo: str) -> Optional[str]:
    """Local path to a tool-aware chat template when the GGUF lacks one.

    Some community GGUFs embed a stripped chat template with no tool support, so
    the model never sees the tools. We fetch the base model's template once and
    pass it to llama-server.
    """
    item = _find(repo)
    url = item.get("chat_template_url") if item else None
    if not url:
        return None
    cache = Path.home() / ".cache" / "jarvis" / "llama.cpp" / "templates"
    dest = cache / (repo.replace("/", "__") + ".jinja")
    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)
    try:
        import urllib.request

        cache.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis/0.0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            dest.write_bytes(resp.read())
        return str(dest)
    except Exception:  # noqa: BLE001
        return None


def model_path(repo: str, filename: str = "") -> Optional[str]:
    """Local path of a downloaded model (GGUF file, or the MLX snapshot dir)."""
    try:
        if filename:
            from huggingface_hub import try_to_load_from_cache

            path = try_to_load_from_cache(repo_id=repo, filename=filename)
            return path if isinstance(path, str) and Path(path).exists() else None
        from huggingface_hub import snapshot_download

        return snapshot_download(repo_id=repo, local_files_only=True)
    except Exception:  # noqa: BLE001
        return None
