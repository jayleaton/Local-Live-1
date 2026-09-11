from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlsplit

import numpy as np

from jarvis.config import JarvisConfig


class _LoopRunner:
    """Runs a single asyncio loop in a background thread.

    The harness owns long-lived async resources (MCP subprocesses), so all
    requests must share one event loop.
    """

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


def _decode_to_16k(data: bytes) -> np.ndarray:
    from faster_whisper.audio import decode_audio

    return np.asarray(decode_audio(io.BytesIO(data), sampling_rate=16000), dtype=np.float32)


def _to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class JarvisService:
    def __init__(self, cfg: JarvisConfig) -> None:
        from jarvis.cli import _build_harness
        from jarvis.stt.whisper_local import FasterWhisperSTT
        from jarvis.tts.kokoro_tts import KokoroTTS

        self.cfg = cfg
        self._runner = _LoopRunner()
        self.harness = self._runner.submit(_build_harness(cfg, confirmer=None, auto_approve=True))
        self.stt = FasterWhisperSTT(cfg.voice.stt_model, device=cfg.voice.stt_device, compute_type=cfg.voice.stt_compute_type)
        self.tts = self._build_tts()
        self._runner.submit(self.harness.start())
        self._lock = threading.Lock()
        self._streaming = None

    def _build_tts(self):
        backend = getattr(self.cfg.voice, "tts_backend", "kokoro")
        if backend == "chatterbox":
            try:
                from jarvis.tts.chatterbox_tts import ChatterboxTTS, ensure_chatterbox_server, is_ready

                if is_ready():
                    return ChatterboxTTS()
                if ensure_chatterbox_server() is not None or is_ready():
                    return ChatterboxTTS()
            except Exception:
                pass
        from jarvis.tts.kokoro_tts import KokoroTTS

        return KokoroTTS(voice=self.cfg.voice.tts_voice, speed=self.cfg.voice.speech_speed)

    @property
    def streaming_stt(self):
        if self._streaming is None:
            from jarvis.stt.sherpa_streaming import SherpaStreamingSTT

            # Match the configured endpointing so a natural pause mid-sentence
            # doesn't end the turn and split one utterance into several messages.
            trailing = max(1.0, float(self.cfg.voice.endpointing_ms) / 1000.0)
            self._streaming = SherpaStreamingSTT(trailing_silence=trailing)
        return self._streaming

    async def respond_streaming(self, text: str):
        """Yield UI events for a turn: thinking, assistant_delta, tool, audio, done."""
        import re

        from jarvis.tts.base import to_speech_text

        buffer = ""
        spoken_any = False
        spoken_count = 0
        full = ""
        tools: list[str] = []
        yield {"type": "thinking"}

        def complete_sentences(buf: str) -> tuple[list[str], str]:
            parts = re.split(r"(?<=[.!?])\s+", buf)
            if len(parts) <= 1:
                if buf.rstrip() and buf.rstrip()[-1] in ".!?":
                    return [buf.strip()], ""
                return [], buf
            return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]

        async def synth_for(sentence: str) -> Optional[str]:
            spoken = to_speech_text(sentence).strip()
            if not spoken:
                return None
            wav = await asyncio.to_thread(self._synth, spoken)
            return base64.b64encode(wav).decode("ascii") if wav else None

        cap = max(1, int(self.cfg.voice.max_spoken_sentences))

        # If the request looks tool-shaped, acknowledge immediately (before the
        # model has decided) so there's no dead air while we call out to MCP.
        toolish = re.compile(
            r"\b(search|weather|news|look ?up|google|list|show me|start|create|open|thread|"
            r"project|fetch|read|github|repo|email|send|schedule|remind|book|order|play|check)\b",
            re.IGNORECASE,
        )
        if toolish.search(text):
            ack = "Yeah, let me check on that."
            audio = await synth_for(ack)
            full += ack + " "
            yield {"type": "assistant_delta", "text": ack + " "}
            if audio:
                yield {"type": "audio", "audio": audio, "text": ack}
            spoken_any = True

        async for event in self.harness.run_stream(text):
            etype = event["type"]
            if etype == "assistant_delta":
                chunk = event["text"]
                buffer += chunk
                full += chunk
                yield {"type": "assistant_delta", "text": chunk}
                sentences, buffer = complete_sentences(buffer)
                for sentence in sentences:
                    if spoken_count < cap:
                        audio = await synth_for(sentence)
                        if audio:
                            yield {"type": "audio", "audio": audio, "text": sentence}
                        spoken_count += 1
                    spoken_any = True
            elif etype == "tool_start":
                tools.append(event["tool"])
                yield {"type": "tool", "name": event["tool"]}
                if not spoken_any:
                    ack = "Let me check on that."
                    audio = await synth_for(ack)
                    full += ack + " "
                    yield {"type": "assistant_delta", "text": ack + " "}
                    if audio:
                        yield {"type": "audio", "audio": audio, "text": ack}
                    spoken_any = True
            elif etype == "done":
                remainder = to_speech_text(buffer).strip()
                if remainder and spoken_count < cap:
                    audio = await synth_for(remainder)
                    if audio:
                        yield {"type": "audio", "audio": audio, "text": remainder}
                    spoken_count += 1
                yield {
                    "type": "done",
                    "text": event.get("text") or full,
                    "tools": tools or event.get("tools", []),
                    "cancelled": event.get("cancelled", False),
                }

    def _make_provider(self):
        if self.cfg.response_mode == "api" or self.cfg.local is None:
            from jarvis.llm.openai_compat import OpenAICompatProvider

            m = self.cfg.model
            return OpenAICompatProvider(
                m.base_url,
                m.model,
                api_key=m.resolved_api_key(),
                timeout=m.timeout,
                name=f"api:{m.model}",
                extra_params=m.extra_params,
                reasoning_effort=m.reasoning_effort,
                strict_tools=m.strict_tools,
            )
        from jarvis.llm.mlx_local import MLXProvider

        return MLXProvider(self.cfg.local.model, temperature=self.cfg.local.temperature, max_tokens=self.cfg.local.max_tokens)

    def warmup(self) -> None:
        """Load models now and keep them resident so the first turn isn't slow."""
        import time

        t0 = time.time()
        notes: list[str] = []
        try:
            provider = self.harness.provider
            if hasattr(provider, "_load"):
                provider._load()
                notes.append("brain")
        except Exception as e:  # noqa: BLE001
            notes.append(f"brain:err({type(e).__name__})")
        for label, obj in (("stt", self.stt), ("tts", self.tts)):
            try:
                if hasattr(obj, "_load"):
                    obj._load()
                    notes.append(label)
            except Exception as e:  # noqa: BLE001
                notes.append(f"{label}:err({type(e).__name__})")
        # Streaming ASR is lazy by default; loading it here means the first push
        # of the mic button is instant (and the model download is visible) instead
        # of racing a download inside the WebSocket handler.
        if getattr(self.cfg.voice, "streaming", True) and getattr(self.cfg.voice, "streaming_backend", "sherpa") == "sherpa":
            print("  loading streaming ASR (first run downloads the model)...")
            try:
                self.streaming_stt._load()
                notes.append("streaming-asr")
            except Exception as e:  # noqa: BLE001 - voice is optional
                notes.append(f"streaming-asr:err({type(e).__name__}: {e})")
        print(f"  warmup: loaded {', '.join(notes) or 'nothing'} in {time.time() - t0:.1f}s")

    def get_settings(self) -> dict:
        return {
            "response_mode": self.cfg.response_mode,
            "local_model": self.cfg.local.model if self.cfg.local else None,
            "local_models": [
                "mlx-community/Qwen3.5-4B-MLX-4bit",
                "mlx-community/Qwen3.5-9B-MLX-4bit",
                "mlx-community/Qwen2.5-3B-Instruct-4bit",
            ],
            "api_model": self.cfg.model.model,
            "api_base_url": self.cfg.model.base_url,
            "tts_voice": self.cfg.voice.tts_voice,
            "tts_backend": getattr(self.cfg.voice, "tts_backend", "kokoro"),
            "tts_backends": ["chatterbox", "kokoro"],
            "voices": ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael", "am_adam", "bm_george", "bf_emma"],
            "max_spoken_sentences": self.cfg.voice.max_spoken_sentences,
            "endpointing_ms": self.cfg.voice.endpointing_ms,
            "asr_backend": self.cfg.voice.streaming_backend,
            "asr_backends": self._asr_backends(),
            "brain": self.harness.provider.name,
            "tools": sorted(t.name for t in self.harness.runtime.tools()),
            "servers": sorted(c.name for c in self.cfg.servers.values() if c.enabled),
        }

    @staticmethod
    def _asr_backends() -> list[dict]:
        """Advertise the selectable speech-to-text backends and their availability."""
        try:
            from jarvis.stt.nemotron_server import find_binary

            nemo_available = find_binary() is not None
        except Exception:  # noqa: BLE001
            nemo_available = False
        return [
            {"value": "sherpa", "label": "Sherpa Zipformer (fast, offline)", "available": True},
            {"value": "nemotron", "label": "NVIDIA Nemotron 3.5 streaming", "available": nemo_available},
        ]

    def apply_settings(self, data: dict) -> dict:
        if data.get("response_mode") in ("local", "api"):
            self.cfg.response_mode = data["response_mode"]
        if data.get("asr_backend") in ("nemotron", "sherpa"):
            self.cfg.voice.streaming_backend = data["asr_backend"]
        if data.get("local_model") and self.cfg.local is not None:
            self.cfg.local.model = data["local_model"]
        if data.get("api_model"):
            self.cfg.model.model = data["api_model"]
        if data.get("tts_backend") in ("chatterbox", "kokoro") and data["tts_backend"] != getattr(self.cfg.voice, "tts_backend", None):
            self.cfg.voice.tts_backend = data["tts_backend"]
            self.tts = self._build_tts()
        if data.get("tts_voice"):
            self.cfg.voice.tts_voice = data["tts_voice"]
            if hasattr(self.tts, "voice"):
                self.tts.voice = data["tts_voice"]
        if data.get("max_spoken_sentences") is not None:
            self.cfg.voice.max_spoken_sentences = max(1, int(data["max_spoken_sentences"]))
        if data.get("endpointing_ms") is not None:
            self.cfg.voice.endpointing_ms = max(100, int(data["endpointing_ms"]))
        # Swap the response provider live.
        self.harness.provider = self._make_provider()
        self._persist()
        return self.get_settings()

    def _persist(self) -> None:
        import json
        from pathlib import Path

        path = Path("jarvis.config.json")
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
        data["response_mode"] = self.cfg.response_mode
        data.setdefault("local", {})["model"] = self.cfg.local.model if self.cfg.local else ""
        data.setdefault("model", {})["model"] = self.cfg.model.model
        data.setdefault("voice", {})["tts_voice"] = self.cfg.voice.tts_voice
        data["voice"]["tts_backend"] = getattr(self.cfg.voice, "tts_backend", "kokoro")
        data["voice"]["streaming_backend"] = self.cfg.voice.streaming_backend
        data["voice"]["max_spoken_sentences"] = self.cfg.voice.max_spoken_sentences
        data["voice"]["endpointing_ms"] = self.cfg.voice.endpointing_ms
        try:
            path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    async def respond(self, text: str) -> dict:
        from jarvis.tts.base import to_speech_text

        result = await self.harness.run(text)
        spoken = self._cap_speech(to_speech_text(result.text))
        wav = await asyncio.to_thread(self._synth, spoken) if spoken else b""
        return {
            "transcript": text,
            "reply": result.text,
            "tools": [r.call.name for r in result.tool_records],
            "audio": base64.b64encode(wav).decode("ascii") if wav else None,
        }

    async def chat(self, text: str) -> dict:
        from jarvis.tts.base import to_speech_text

        result = await self.harness.run(text)
        spoken = self._cap_speech(to_speech_text(result.text))
        wav = await asyncio.to_thread(self._synth, spoken) if spoken else b""
        out = self._result(text, result.text, result)
        out["audio"] = base64.b64encode(wav).decode("ascii") if wav else None
        return out

    async def voice(self, data: bytes) -> dict:
        audio = await asyncio.to_thread(_decode_to_16k, data)
        transcript = (await asyncio.to_thread(self.stt.transcribe, audio, 16000)).strip()
        if not transcript:
            return {"transcript": "", "reply": "", "audio": None, "tools": []}
        result = await self.harness.run(transcript)
        from jarvis.tts.base import to_speech_text

        spoken = to_speech_text(result.text)
        wav = await asyncio.to_thread(self._synth, spoken) if spoken else b""
        return {
            "transcript": transcript,
            "reply": result.text,
            "audio": base64.b64encode(wav).decode("ascii") if wav else None,
            "tools": [r.call.name for r in result.tool_records],
        }

    def _synth(self, text: str) -> bytes:
        audio = self.tts.synthesize(text)
        return _to_wav(audio, self.tts.sample_rate)

    def _cap_speech(self, text: str) -> str:
        from jarvis.tts.base import split_sentences

        cap = max(1, int(self.cfg.voice.max_spoken_sentences))
        sentences = split_sentences(text)
        if len(sentences) <= cap:
            return text.strip()
        return " ".join(sentences[:cap]).strip()

    @staticmethod
    def _result(transcript: str, reply: str, result) -> dict:
        return {
            "transcript": transcript,
            "reply": reply,
            "audio": None,
            "tools": [r.call.name for r in result.tool_records],
            "denied": result.denied,
        }

    def speak(self, text: str) -> Optional[str]:
        with self._lock:
            from jarvis.tts.base import to_speech_text

            spoken = to_speech_text(text)
            if not spoken:
                return None
            return base64.b64encode(self._synth(spoken)).decode("ascii")

    def stop(self) -> None:
        try:
            self._runner.submit(self.harness.stop())
        except Exception:
            pass

    def start_ws(self, host: str, port: int) -> None:
        import numpy as np

        async def sherpa_handler(ws) -> None:
            import json
            import traceback

            stt = self.streaming_stt
            try:
                stream = await asyncio.to_thread(stt.create_stream)
            except Exception as e:  # noqa: BLE001 - report to the UI, don't kill the handler silently
                traceback.print_exc()
                try:
                    await ws.send(json.dumps({"type": "error", "text": f"Speech model unavailable: {e}"}))
                except Exception:
                    pass
                return

            async def finalize() -> None:
                final = (await asyncio.to_thread(stt.text, stream)).strip()
                await asyncio.to_thread(stt.reset, stream)
                if not final:
                    return
                await ws.send(json.dumps({"type": "transcript", "text": final}))
                async for event in self.respond_streaming(final):
                    await ws.send(json.dumps(event))

            try:
                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        pcm = np.frombuffer(bytes(msg), dtype=np.int16)
                        await asyncio.to_thread(stt.accept, stream, pcm)
                        text = await asyncio.to_thread(stt.text, stream)
                        if await asyncio.to_thread(stt.is_endpoint, stream):
                            await finalize()
                        elif text:
                            await ws.send(json.dumps({"type": "partial", "text": text}))
                    elif isinstance(msg, str):
                        try:
                            cmd = json.loads(msg)
                        except json.JSONDecodeError:
                            cmd = {}
                        kind = cmd.get("type")
                        if kind == "reset":
                            await asyncio.to_thread(stt.reset, stream)
                        elif kind == "finalize":
                            await finalize()
            except Exception:
                traceback.print_exc()

        async def nemotron_handler(ws) -> None:
            import json
            import traceback

            import websockets

            url = self.cfg.voice.nemo_url.rstrip("/") + "/v1/audio/transcriptions/realtime"
            from jarvis.stt.nemotron_server import ensure_nemo_server, is_ready

            http_base = self.cfg.voice.nemo_url.replace("ws://", "http://").replace("wss://", "https://")
            if not is_ready(http_base):
                try:
                    await asyncio.to_thread(
                        ensure_nemo_server, self.cfg.voice.nemo_url, self.cfg.voice.nemo_model, log_path="logs/nemo.log"
                    )
                except Exception:
                    pass
            try:
                nws = await websockets.connect(url, max_size=None)
            except Exception:
                return await sherpa_handler(ws)

            async with nws:
                accum = {"text": ""}
                try:
                    await asyncio.wait_for(nws.recv(), timeout=5)  # session.created
                    await nws.send(
                        json.dumps(
                            {
                                "type": "session.update",
                                "session": {"endpointing_ms": self.cfg.voice.endpointing_ms},
                            }
                        )
                    )
                    await asyncio.wait_for(nws.recv(), timeout=5)  # session.updated
                except Exception:
                    pass

                async def browser_to_nemo() -> None:
                    async for msg in ws:
                        if isinstance(msg, (bytes, bytearray)):
                            await nws.send(bytes(msg))
                        elif isinstance(msg, str):
                            try:
                                cmd = json.loads(msg)
                            except json.JSONDecodeError:
                                cmd = {}
                            kind = cmd.get("type")
                            if kind == "finalize":
                                try:
                                    await nws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                                except Exception:
                                    pass
                            elif kind == "reset":
                                accum["text"] = ""
                                try:
                                    await nws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                                except Exception:
                                    pass

                async def nemo_to_browser() -> None:
                    async for raw in nws:
                        if isinstance(raw, (bytes, bytearray)):
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        etype = event.get("type", "")
                        if etype.endswith("input_audio_transcription.delta"):
                            delta = event.get("delta") or ""
                            if delta:
                                accum["text"] += delta
                                await ws.send(json.dumps({"type": "partial", "text": accum["text"]}))
                        elif etype.endswith("input_audio_transcription.completed"):
                            final = (event.get("transcript") or accum["text"]).strip()
                            accum["text"] = ""
                            if final:
                                await ws.send(json.dumps({"type": "transcript", "text": final}))
                                async for out in self.respond_streaming(final):
                                    await ws.send(json.dumps(out))
                        elif etype.endswith("speech_started"):
                            try:
                                await ws.send(json.dumps({"type": "speech_started"}))
                            except Exception:
                                pass

                t1 = asyncio.create_task(browser_to_nemo())
                t2 = asyncio.create_task(nemo_to_browser())
                try:
                    await asyncio.gather(t1, t2)
                except Exception:
                    traceback.print_exc()
                finally:
                    for t in (t1, t2):
                        t.cancel()

        async def _route(ws) -> None:
            # Read the backend per connection so a Settings change applies to the
            # next mic session without restarting the server.
            if getattr(self.cfg.voice, "streaming_backend", "sherpa") == "nemotron":
                await nemotron_handler(ws)
            else:
                await sherpa_handler(ws)

        async def _serve() -> None:
            import websockets

            self._ws_server = await websockets.serve(_route, host, port, max_size=None)

        self._runner.submit(_serve())



def _handler_for(service: JarvisService, index_html: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quieter
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def do_GET(self):  # noqa: N802
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, index_html.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/health":
                self._json(200, {"ok": True})
            elif path == "/settings":
                self._json(200, service.get_settings())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            try:
                if path == "/chat":
                    payload = json.loads(data.decode("utf-8") or "{}")
                    text = (payload.get("text") or "").strip()
                    if not text:
                        self._json(400, {"error": "empty text"})
                        return
                    self._json(200, service._runner.submit(service.chat(text)))
                elif path == "/voice":
                    self._json(200, service._runner.submit(service.voice(data)))
                elif path == "/speak":
                    payload = json.loads(data.decode("utf-8") or "{}")
                    self._json(200, {"audio": service.speak(payload.get("text") or "")})
                elif path == "/settings":
                    payload = json.loads(data.decode("utf-8") or "{}")
                    self._json(200, service.apply_settings(payload))
                else:
                    self._send(404, b"not found", "text/plain")
            except Exception as e:  # noqa: BLE001
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def _interface_ips() -> list[str]:
    import re
    import subprocess

    if os.name == "nt":
        cmd, pattern = ["ipconfig"], r"IPv4[^\d]*(\d+\.\d+\.\d+\.\d+)"
    else:
        cmd, pattern = ["ifconfig"], r"inet (\d+\.\d+\.\d+\.\d+)"
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    return re.findall(pattern, out)


def _urls(host: str, port: int, scheme: str = "https") -> list[str]:
    urls = [f"{scheme}://127.0.0.1:{port}"]
    if host in ("0.0.0.0", "::", ""):
        seen: set[str] = set()
        for ip in _interface_ips():
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            if ip.startswith("100."):
                urls.append(f"{scheme}://{ip}:{port}   (tailscale)")
            elif ip.startswith(("192.168.", "10.")):
                urls.append(f"{scheme}://{ip}:{port}   (lan)")
    return urls


def _ensure_cert(cert_dir) -> Optional[tuple[str, str]]:
    """Create a self-signed cert (SANs for localhost/tailscale/lan) if missing.

    getUserMedia requires a secure context, so plain HTTP over Tailscale can't
    access the mic. Self-signed HTTPS works once the browser warning is accepted.

    Returns ``None`` when no certificate can be produced (e.g. ``openssl`` is not
    installed on Windows); callers then fall back to plain HTTP.
    """
    import shutil
    import subprocess
    from pathlib import Path

    if shutil.which("openssl") is None:
        return None

    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert = cert_dir / "cert.pem"
    key = cert_dir / "key.pem"
    if cert.exists() and key.exists():
        return str(cert), str(key)

    import socket

    hosts = {"localhost", socket.gethostname(), socket.gethostname().split(".")[0]}
    for h in os.environ.get("JARVIS_CERT_HOSTS", "").split(","):
        h = h.strip()
        if h:
            hosts.add(h)
    names = {f"DNS:{h}" for h in hosts if h}
    names.add("IP:127.0.0.1")
    for ip in _interface_ips():
        names.add(f"IP:{ip}")
    san = ",".join(sorted(names))
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "825", "-nodes", "-subj", "/CN=jarvis",
                "-addext", f"subjectAltName={san}",
            ],
            check=True, capture_output=True,
        )
    except Exception:  # noqa: BLE001 - fall back to HTTP rather than crash
        cert.unlink(missing_ok=True)
        key.unlink(missing_ok=True)
        return None
    return str(cert), str(key)


def run_server(
    cfg: JarvisConfig,
    host: str = "0.0.0.0",
    port: int = 8765,
    *,
    open_browser: bool = True,
    https: bool = True,
    cert_dir: str = "logs/certs",
    streaming: bool = True,
) -> None:
    import ssl
    import webbrowser

    from jarvis.web.page import INDEX_HTML

    service = JarvisService(cfg)
    httpd = None
    chosen = port
    for candidate in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((host, candidate), _handler_for(service, INDEX_HTML))
            chosen = candidate
            break
        except OSError as e:
            if getattr(e, "errno", None) in (48, 98):  # address already in use
                continue
            raise
    if httpd is None:
        raise RuntimeError(f"no free port in range {port}-{port + 19}")

    scheme = "http"
    if https:
        cert = _ensure_cert(cert_dir)
        if cert is None:
            print("  (openssl unavailable: serving HTTP — the mic works on localhost; use Tailscale for remote HTTPS)")
        else:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(*cert)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
            scheme = "https"

    if chosen != port:
        print(f"Port {port} was busy; using {chosen} instead.")
    print(f"Jarvis web UI (bound to all interfaces, {'HTTPS' if scheme == 'https' else 'HTTP'}):")
    for u in _urls(host, chosen, scheme):
        print("  ", u)
    print(f"  brain={service.harness.provider.name}  workers={list(cfg.agents)}")
    if streaming:
        backend = cfg.voice.streaming_backend
        if backend == "nemotron":
            from jarvis.stt.nemotron_server import ensure_nemo_server, find_binary

            try:
                if find_binary() is None:
                    raise RuntimeError("nemo-speech not installed")
                proc = ensure_nemo_server(cfg.voice.nemo_url, cfg.voice.nemo_model, log_path="logs/nemo.log")
                print(f"  ASR: nemotron-3.5 streaming ({'started' if proc else 'reused'}) @ {cfg.voice.nemo_url}")
            except Exception as e:  # noqa: BLE001 - Nemotron is optional
                cfg.voice.streaming_backend = "sherpa"
                print(f"  ASR: nemotron unavailable ({e}); using sherpa-onnx zipformer")
        else:
            print("  ASR: sherpa-onnx streaming zipformer")
        ws_port = cfg.voice.streaming_ws_port or (chosen + 1)
        try:
            service.start_ws(host, ws_port)
            print(f"  streaming bridge on :{ws_port}")
        except Exception as e:  # noqa: BLE001
            print(f"  streaming unavailable ({type(e).__name__}: {e}); using VAD+Whisper")
    if scheme == "https":
        print("  (self-signed cert: accept the browser warning once — the mic needs a secure context)")
    service.warmup()
    print("  Ctrl-C to stop.")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"{scheme}://127.0.0.1:{chosen}")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        service.stop()
