from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

BIN_CANDIDATES = [
    os.environ.get("NEMO_SPEECH_BIN", ""),
    # NVIDIA's Windows installer default (%LOCALAPPDATA%\Programs\NeMoSpeech).
    str(Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Programs/NeMoSpeech/bin/nemo-speech.exe")
    if os.name == "nt"
    else "",
    # Linux/macOS installer default prefix.
    str(Path.home() / ".local/opt/nemo-speech/nemo-speech/bin/nemo-speech"),
    str(Path.home() / ".local/bin/nemo-speech"),
    "nemo-speech",
]


def find_binary() -> Optional[str]:
    """Return a usable nemo-speech path, or None. Never returns a path that doesn't exist."""
    for candidate in BIN_CANDIDATES:
        if not candidate:
            continue
        if os.path.dirname(candidate):  # explicit path
            if os.path.exists(candidate):
                return candidate
        else:  # bare name: resolve on PATH
            found = shutil.which(candidate)
            if found:
                return found
    return None


def is_ready(http_base: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(http_base.rstrip("/") + "/ready", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_nemo_server(
    ws_url: str = "ws://127.0.0.1:8081",
    model: str = "nemotron-3.5",
    *,
    log_path: str = "logs/nemo.log",
    timeout: float = 120.0,
) -> Optional[subprocess.Popen]:
    """Start `nemo-speech serve` if it's installed and not already reachable.

    Returns the Popen if we started it, else None (already running, or not
    installed). Never raises: Nemotron is optional and must not take down the
    backend when absent.
    """
    http_base = ws_url.replace("ws://", "http://").replace("wss://", "https://")
    if is_ready(http_base):
        return None
    binary = find_binary()
    if not binary:
        return None
    host = http_base.split("//", 1)[1].split(":")[0]
    port = http_base.rstrip("/").rsplit(":", 1)[-1]

    log: object
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "ab")  # noqa: SIM115 - kept open for the child process
    except Exception:
        log = subprocess.DEVNULL

    kwargs: dict = {"stdout": log, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen([binary, "serve", "--asr-model", model, "--host", host, "--port", str(port)], **kwargs)
    except Exception:
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        if is_ready(http_base):
            return proc
        time.sleep(1.5)
    return proc
