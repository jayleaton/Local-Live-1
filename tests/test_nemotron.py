from __future__ import annotations

from jarvis.stt import nemotron_server as ns


def test_find_binary_returns_none_when_absent(monkeypatch):
    # A bare name that isn't on PATH must NOT be returned (this caused a Windows crash).
    monkeypatch.setattr(ns, "BIN_CANDIDATES", ["definitely-not-a-real-nemo-binary"])
    monkeypatch.setattr(ns.shutil, "which", lambda _name: None)
    assert ns.find_binary() is None


def test_find_binary_uses_which_for_bare_names(monkeypatch):
    monkeypatch.setattr(ns, "BIN_CANDIDATES", ["nemo-speech"])
    monkeypatch.setattr(ns.shutil, "which", lambda name: "/opt/bin/nemo-speech" if name == "nemo-speech" else None)
    assert ns.find_binary() == "/opt/bin/nemo-speech"


def test_find_binary_requires_explicit_paths_to_exist(monkeypatch):
    monkeypatch.setattr(ns, "BIN_CANDIDATES", ["/nope/nemo-speech"])
    assert ns.find_binary() is None


def test_ensure_nemo_server_without_binary_is_none(monkeypatch):
    monkeypatch.setattr(ns, "BIN_CANDIDATES", ["definitely-not-a-real-nemo-binary"])
    monkeypatch.setattr(ns.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ns, "is_ready", lambda *_a, **_k: False)
    assert ns.ensure_nemo_server() is None
