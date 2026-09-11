from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

BIN_CANDIDATES = [
    os.environ.get("NEMO_SPEECH_BIN", ""),
    str(Path.home() / ".local/opt/nemo-speech/nemo-speech/bin/nemo-speech"),
    str(Path.home() / ".local/bin/nemo-speech"),
    "nemo-speech",
]


def find_binary() -> Optional[str]:
    for candidate in BIN_CANDIDATES:
        if candidate and (os.path.sep in candidate or candidate == "nemo-speech"):
            if candidate == "nemo-speech" or os.path.exists(candidate):
                return candidate
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
    """Start `nemo-speech serve` if it isn't already reachable.

    Returns the Popen handle if we started it, else None (already running or
    binary missing).
    """
    http_base = ws_url.replace("ws://", "http://").replace("wss://", "https://")
    if is_ready(http_base):
        return None
    binary = find_binary()
    if not binary:
        return None
    host = http_base.split("//", 1)[1].split(":")[0]
    port = http_base.rstrip("/").rsplit(":", 1)[-1]

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")  # noqa: SIM115 - kept open for the child process
    proc = subprocess.Popen(
        [binary, "serve", "--asr-model", model, "--host", host, "--port", str(port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        if is_ready(http_base):
            return proc
        time.sleep(1.5)
    return proc
