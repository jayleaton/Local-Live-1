#!/usr/bin/env python3
"""Chatterbox-Turbo TTS sidecar.

Runs in its own venv (.venv-tts) because it needs torch, which we keep out of
the main environment. Exposes a tiny HTTP API:

    GET  /health           -> {"ok": true}
    POST /speak  {text}    -> audio/wav (24 kHz mono)

Started automatically by `jarvis serve` when voice.tts_backend == "chatterbox".
"""
from __future__ import annotations

import io
import json
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

_MODEL = None


def _load() -> None:
    global _MODEL
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    _MODEL = ChatterboxTurboTTS.from_pretrained(device="cpu")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # noqa: D102
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, b'{"ok": true}', "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/speak":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        text = (payload.get("text") or "").strip()
        if not text:
            self._send(400, b'{"error":"empty text"}', "application/json")
            return
        reference = payload.get("reference") or None
        try:
            wav = _MODEL.generate(text, audio_prompt_path=reference) if reference else _MODEL.generate(text)
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
            return
        arr = wav.detach().cpu().numpy().reshape(-1)
        pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm.tobytes())
        self._send(200, buf.getvalue(), "audio/wav")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8082)
    args = parser.parse_args()
    print("loading Chatterbox-Turbo (cpu)...", flush=True)
    _load()
    print(f"chatterbox ready on http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
