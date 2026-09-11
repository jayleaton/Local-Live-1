from __future__ import annotations

from pathlib import Path

from jarvis.stt import nemo_models as nm


def test_cache_dir_is_platform_specific():
    assert nm.cache_dir("windows", {"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}).parts[-2:] == ("NeMoSpeech", "models")
    assert nm.cache_dir("darwin", {}).parts[-2:] == ("NeMoSpeech", "models")
    assert nm.cache_dir("linux", {"XDG_CACHE_HOME": "/tmp/xdg"}).parts[-1] == "models"
    assert nm.cache_dir(env={"NEMO_SPEECH_MODEL_DIR": "/models/here"}) == Path("/models/here")


def test_is_downloaded_matches_name_and_size(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "model.q8_0.gguf").write_bytes(b"x" * 100)
    assert nm.is_downloaded("model.q8_0.gguf", 100, root=tmp_path) is True
    assert nm.is_downloaded("model.q8_0.gguf", 101, root=tmp_path) is False
    assert nm.is_downloaded("missing.gguf", 1, root=tmp_path) is False
    assert nm.is_downloaded("", 1, root=tmp_path) is False


def test_entry_extracts_asr_metadata(monkeypatch):
    monkeypatch.setattr(nm, "is_downloaded", lambda *a, **k: True)
    model = {
        "repo": "nvidia/nemotron-3.5-asr-streaming-0.6b",
        "aliases": ["nemotron-3.5", "nemotron-asr"],
        "license": "OpenMDW",
        "artifacts": [
            {"role": "diarization", "filename": "nope.gguf", "size": 1},
            {"role": "asr", "filename": "nemotron.gguf", "size": 741_548_352},
        ],
    }
    entry = nm._entry(model)
    assert entry["name"] == "nemotron-3.5"
    assert entry["filename"] == "nemotron.gguf"
    assert entry["streaming"] is True
    assert entry["downloaded"] is True
    assert entry["size_mb"] and entry["size_mb"] > 700


def test_is_installed_requires_expected_size(tmp_path: Path):
    repo = "nvidia/nemotron-3.5-asr-streaming-0.6b"
    rev = tmp_path / "nvidia" / "nemotron-3.5-asr-streaming-0.6b" / "rev1"
    rev.mkdir(parents=True)
    (rev / "model.gguf").write_bytes(b"x" * 100)
    assert nm.is_installed(repo, 100, root=tmp_path) is True
    assert nm.is_installed(repo, 1000, root=tmp_path) is False  # partial download
    assert nm.is_installed("nvidia/nemotron-speech-streaming-en-0.6b", 1, root=tmp_path) is False
    assert nm.cached_bytes(repo, root=tmp_path) == 100


def test_entry_handles_cli_roles_shape(monkeypatch):
    # `nemo-speech --json model list` reports roles/aliases, not artifacts/size.
    monkeypatch.setattr(nm, "is_installed", lambda *a, **k: False)
    entry = nm._entry(
        {
            "repo": "nvidia/nemotron-3.5-asr-streaming-0.6b",
            "aliases": ["nemotron-3.5", "nemotron-asr"],
            "roles": ["asr"],
            "license": "OpenMDW",
        }
    )
    assert entry["name"] == "nemotron-3.5"
    assert entry["streaming"] is True
    assert entry["size_mb"] and entry["size_mb"] > 700
    assert entry["downloaded"] is False
    assert nm._entry({"repo": "nvidia/magpie", "roles": ["tts"]}) is None


def test_entry_marks_parakeet_offline(monkeypatch):
    monkeypatch.setattr(nm, "is_downloaded", lambda *a, **k: False)
    entry = nm._entry(
        {
            "repo": "nvidia/parakeet-tdt-0.6b-v3",
            "aliases": ["parakeet-tdt"],
            "artifacts": [{"role": "asr", "filename": "p.gguf", "size": 10}],
        }
    )
    assert entry["streaming"] is False
    assert "offline" in entry["label"].lower()


def test_iter_index_models_accepts_both_shapes():
    nested = {"schema_version": 1, "models": [{"repo": "r", "artifacts": []}]}
    assert len(list(nm._iter_index_models(nested))) == 1
    categorized = {"asr": [{"repo": "r1"}], "tts": [{"repo": "r2"}]}
    assert len(list(nm._iter_index_models(categorized))) == 2


def test_list_models_without_runtime(monkeypatch):
    monkeypatch.setattr(nm, "find_binary", lambda: None)
    info = nm.list_models()
    assert info["runtime_installed"] is False
    assert info["models"] == []


def test_parse_percent():
    assert nm.parse_percent("downloading 42%") == 42
    assert nm.parse_percent("100%") == 100
    assert nm.parse_percent("no progress here") is None
