from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from jarvis.stt import sherpa_streaming as ss  # noqa: E402

REQUIRED = [
    "tokens.txt",
    "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
    "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
    "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
]


def _write_tar(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:bz2") as tar:
        for name in names:
            data = b"x" * 32
            info = tarfile.TarInfo(f"{ss.MODEL_NAME}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_model_complete_requires_every_part(tmp_path: Path) -> None:
    cache = tmp_path / ss.MODEL_NAME
    cache.mkdir()
    (cache / "tokens.txt").write_text("a")
    assert ss._model_complete(cache) is False
    for name in REQUIRED:
        (cache / name).write_text("x")
    assert ss._model_complete(cache) is True


def test_ensure_model_replaces_partial_extraction(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "sherpa"
    cache = base / ss.MODEL_NAME
    cache.mkdir(parents=True)
    # A previous interrupted run left a partial model that looks "present".
    (cache / "tokens.txt").write_text("stale")
    (cache / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx").write_text("stale")

    def fake_download(url, dest, on_progress=None, retries=3):  # noqa: ANN001
        _write_tar(dest, REQUIRED)

    monkeypatch.setattr(ss, "_download", fake_download)

    result = ss.ensure_model(base)

    assert result == cache
    assert ss._model_complete(cache)
    # no leftover temp dirs or archives next to the model
    leftovers = [p.name for p in base.iterdir() if p.name.startswith(".") or p.suffix == ".bz2"]
    assert leftovers == []


def test_ensure_model_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "sherpa"
    calls: list[str] = []

    def fake_download(url, dest, on_progress=None, retries=3):  # noqa: ANN001
        calls.append(str(dest))
        _write_tar(dest, REQUIRED)

    monkeypatch.setattr(ss, "_download", fake_download)

    ss.ensure_model(base)
    ss.ensure_model(base)
    assert len(calls) == 1
