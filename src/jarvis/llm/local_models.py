"""On-device (MLX) model catalog and downloader.

Mirrors the speech-model flow: list the candidate brain models, tell whether
each is already in the Hugging Face cache, and download on demand with progress
computed from the cache size. ``huggingface_hub`` is optional, so every import is
guarded and callers degrade gracefully.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

CATALOG = [
    {"repo": "mlx-community/Qwen3.5-4B-MLX-4bit", "label": "Qwen3.5 4B (MLX 4-bit)"},
    {"repo": "mlx-community/Qwen3.5-9B-MLX-4bit", "label": "Qwen3.5 9B (MLX 4-bit)"},
    {"repo": "mlx-community/Qwen2.5-3B-Instruct-4bit", "label": "Qwen2.5 3B Instruct (MLX 4-bit)"},
]

_sizes: dict[str, int] = {}
_size_lock = threading.Lock()


def _label(repo: str) -> str:
    for item in CATALOG:
        if item["repo"] == repo:
            return item["label"]
    return repo.split("/")[-1]


def total_size(repo: str) -> int:
    """Total bytes of the repo on the Hub (cached in memory; 0 when offline)."""
    with _size_lock:
        if repo in _sizes:
            return _sizes[repo]
    size = 0
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo, files_metadata=True)
        size = sum(int(f.size or 0) for f in (info.siblings or []))
    except Exception:  # noqa: BLE001 - offline / gated repo
        size = 0
    with _size_lock:
        _sizes[repo] = size
    return size


def cached_bytes(repo: str) -> int:
    try:
        from huggingface_hub import scan_cache_dir

        total = 0
        for entry in scan_cache_dir().repos:
            if entry.repo_id == repo:
                for rev in entry.revisions:
                    total += int(rev.size_on_disk)
        return total
    except Exception:  # noqa: BLE001
        return 0


def is_downloaded(repo: str, size: int = 0) -> bool:
    total = cached_bytes(repo)
    if total == 0:
        return False
    expected = size or total_size(repo)
    if expected:
        return total >= int(expected * 0.98)
    return True


def list_models() -> list[dict]:
    out = []
    for item in CATALOG:
        repo = item["repo"]
        size = total_size(repo)
        out.append(
            {
                "repo": repo,
                "name": repo,
                "label": item["label"],
                "size": size,
                "size_mb": round(size / 1e6, 1) if size else None,
                "downloaded": is_downloaded(repo, size),
            }
        )
    return out


def pull(repo: str, on_progress: Optional[Callable[[str], None]] = None, token: Optional[str] = None) -> None:
    from huggingface_hub import snapshot_download

    if on_progress:
        on_progress(f"downloading {repo}")
    snapshot_download(repo_id=repo, token=token)
    if on_progress:
        on_progress("done")
