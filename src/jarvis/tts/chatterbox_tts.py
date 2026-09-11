from __future__ import annotations

import io
import json
import os
import subprocess
import time
import urllib.request
import wave
from typing import Optional

import numpy as np

from jarvis.tts.base import TTS

DEFAULT_URL = "http://127.0.0.1:8082"
SIDECAR = "scripts/chatterbox_server.py"
VENV_PYTHON = ".venv-tts/bin/python"


def is_ready(base_url: str = DEFAULT_URL, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_chatterbox_server(
    base_url: str = DEFAULT_URL,
    *,
    log_path: str = "logs/chatterbox.log",
    timeout: float = 180.0,
) -> Optional[subprocess.Popen]:
    """Start the Chatterbox sidecar (its own venv) if it isn't already running."""
    if is_ready(base_url):
        return None
    python = os.path.join(os.getcwd(), VENV_PYTHON)
    if not os.path.exists(python):
        return None
    port = base_url.rstrip("/").rsplit(":", 1)[-1]
    log = open(log_path, "ab")  # noqa: SIM115
    proc = subprocess.Popen(
        [python, SIDECAR, "--port", port],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        if is_ready(base_url):
            return proc
        time.sleep(2.0)
    return proc


class ChatterboxTTS(TTS):
    """Chatterbox-Turbo via the local sidecar (CPU, ~0.7x realtime)."""

    sample_rate = 24000

    def __init__(self, base_url: str = DEFAULT_URL, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def synthesize(self, text: str, *, voice: str | None = None, speed: float = 1.0) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        body = json.dumps({"text": text, "reference": voice}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/speak", data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read()
        with wave.open(io.BytesIO(data), "rb") as w:
            frames = w.readframes(w.getnframes())
        return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
