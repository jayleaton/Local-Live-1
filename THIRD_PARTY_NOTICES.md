# Third-party notices

Jarvis's own code is MIT (see `LICENSE`). Models and libraries keep their own
licenses. Anything shipped by default should be commercially usable where
possible; check before adopting a new dependency or model.

## Python libraries

| Package | License |
|---|---|
| numpy | BSD-3-Clause |
| sounddevice (+ PortAudio) | MIT |
| webrtcvad-wheels | BSD-3-Clause |
| faster-whisper | MIT |
| CTranslate2 | MIT |
| kokoro-onnx | Apache-2.0 |
| sherpa-onnx | Apache-2.0 |
| websockets | BSD-3-Clause |
| huggingface-hub | Apache-2.0 |
| mlx / mlx-lm | MIT |
| pytest | MIT |

`espeakng-loader`/`espeak-ng` (used by Kokoro G2P) is **GPL-3.0**. It is pulled as a
pip dependency, not vendored; review before distributing a bundled binary.

## Models

| Model | Role | License |
|---|---|---|
| Kokoro-82M | TTS (fallback) | Apache-2.0 |
| Chatterbox-Turbo | TTS (default) | MIT |
| faster-whisper `base.en` | STT (fallback) | MIT (Whisper weights MIT) |
| NVIDIA Nemotron 3.5 ASR Streaming 0.6B | STT (streaming) | OpenMDW-1.1 / NVIDIA Open Model License |
| sherpa-onnx streaming Zipformer (en-2023-06-26) | STT (streaming fallback) | see model card (Apache-2.0 for the repo) |
| Qwen3.5 MLX (4B / 9B) | on-device LLM | Apache-2.0 |

## Optional / user-supplied

- **DeepSeek API** (worker agent) — governed by DeepSeek's terms; not bundled.
- **z.ai MCP servers** (web search/reader/zread) — governed by z.ai's terms; user supplies a key.

Notes on models we evaluated but do **not** ship: OmniVoice (weights CC-BY-NC),
Tencent AuK (MIT code/weights but CUDA-first, not integrated). See `docs/research/`.
