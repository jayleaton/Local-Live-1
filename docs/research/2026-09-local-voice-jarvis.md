# Fully Local, On-Device Jarvis: Feasibility & Architecture Research

**Date:** September 2026
**Status:** Research complete — architecture recommendation and build plan included
**Question:** Can we build the OpenAI-style natural-voice, barge-in ("cut-in") agent experience as a **fully local, on-device** system — with an MCP/tool harness that can also offload to cloud models or other devices — on mid-to-high tier consumer hardware?

> **Architecture update (implementation phase):** the "tool-calling cortex" is **on-device**. The remote API is not a reply provider or a knowledge fallback — it is a set of **worker agents** the on-device model dispatches larger task prompts to (via MCP or a built-in API agent tool), then relays the result. See [ADR 0002](../architecture/adr/0002-local-orchestrator-worker-agents.md). The model/hardware analysis below is unchanged.

---

## TL;DR — Verdict

**Yes, and the hard part is not the voice.** The interesting pivot is that a local "Jarvis" should not be one model doing everything. It should be a small, fast, always-listening **conversational shell** (for naturalness + barge-in) wired to a larger, slower **tool-calling cortex** (for agency), behind a model-agnostic MCP harness.

Three things changed the calculus in 2025–2026:

1. **True full-duplex open models exist now.** Moshi (Kyutai) and PersonaPlex-class models run locally at 7B with ~160–250 ms latency and real interruption handling. MiniCPM-o class omni models bring tool-ish behavior + vision at 9B int4.
2. **The cascaded path got fast enough.** Streaming STT (Moonshine / Voxtral Realtime / Parakeet) + a 4–8B Q4 tool-calling LLM + streaming TTS (Kokoro / Supertonic / Chatterbox Turbo) lands at **~300–900 ms** on a mid-tier laptop, and near **<300 ms** on high-tier hardware.
3. **MCP is now a real local-first substrate.** The `2026-07-28` spec makes Streamable HTTP stateless, adds Tasks (async/durable) and Skills-over-MCP, and stdio remains the default for local servers. The on-device agent can call local tools and selectively offload text to cloud/second devices.

**Recommended path:** build the **harness first** (MCP-native, model-agnostic, streaming), start with a **cascaded pipeline** for reliability and tool use, and add a **full-duplex shell** as the front-end once the harness is solid. Treat the durable streaming cortex as responsible for tools; treat the duplex shell as responsible for *feel*.

**Recommended target hardware for the reference build:** Apple Silicon M-series, M4 Pro 24–48 GB or better (unified memory + Metal/MLX), with NVIDIA 16–24 GB CUDA as the second target. Phones and Snapdragon/NPU are a later, reduced-capability tier.

**Biggest risks:** (a) local 3–8B tool-calling reliability degrades with quantization and multi-step chains; (b) endpointing/turn-taking latency quietly dominates the budget; (c) tool output is untrusted input — a local always-on agent with shell/filesystem MCP servers is an RCE-shaped attack surface. All three are solvable, and the plan below addresses each.

---

## 0. What the reference actually is (and why cloud isn't required)

The triggering thread was OpenAI's **Agents API / Codex harness**: cloud orchestration, managed long-running sessions, context management, and bring-your-own-sandbox. The user's read — "this shouldn't need full cloud-based architecture" — is correct for the *voice* layer, but it is worth separating two different things the cloud currently provides:

| Cloud-provided function | Is it needed locally? | Local replacement |
|---|---|---|
| Realtime natural voice + barge-in | No | Full-duplex model (Moshi/PersonaPlex) or streaming cascaded pipeline with VAD/AEC |
| Long-running orchestration / context management | Partially | On-device harness: state machine, planner/executor, memory store, task queue |
| Managed sandboxes for code/files | Not for a personal assistant | Local sandbox (container/VM) + permission gates |
| Frontier reasoning when needed | Sometimes | Explicit offload router → cloud model or a second device (text-only, redacted) |
| Scale-out / multi-tenant serving | No | Single-user device |

So the goal is not "reimplement OpenAI's infra locally." It is: **keep the voice loop local and instant; make the harness local-first; make cloud a deliberate, permissioned escape hatch rather than the default.**

The one thing cloud still wins clearly on is raw model capability. A local 4B will not out-reason GPT-class models. The architecture below treats that as a routing decision, not a reason to centralize.

---

## 1. Four viable on-device architectures

| # | Architecture | How it works | Voice latency | Tool/agent quality | Hardware floor | Verdict |
|---|---|---|---|---|---|---|
| **A** | **Native full-duplex S2S** | One audio-in/audio-out model (Moshi, PersonaPlex, MiniCPM-o) | **~160–450 ms** | Weak–moderate; only newest (Nemotron-class) do tool calling mid-duplex | 16–24 GB (7–9B q4) | Best *feel*; use as front-end, not the whole brain |
| **B** | **Cascaded** STT → LLM → TTS | Discrete streaming components plus VAD/turn detector | **~300–900 ms** | **Best** — full tool calls, RAG, structured output, long context | 16 GB+ (3–8B q4) | Best *capability*; the reliable backbone |
| **C** | **Split-brain hybrid** (recommended) | Duplex/streaming **shell** owns conversation + barge-in; a tool-calling **cortex** LLM owns agency; harness routes between them | **~250–600 ms** | **Best of both** | 16–24 GB+ | Recommended target |
| **D** | **Browser / WebGPU** | WebLLM/Transformers.js + Web Audio | ~1 s+ | Limited | Any modern browser | Prototype/demo only, not hard-real-time |

**Why C wins.** The mistake to avoid is asking one 7B model to be simultaneously (1) an ultra-low-latency conversationalist and (2) a reliable tool-calling reasoner. Those pull in opposite directions. Instead:

- A **shell** (duplex model *or* a very fast small LLM on a streaming cascade) handles turn-taking, backchannel, and barge-in — the parts users perceive as "alive."
- A **cortex** (4–32B, whatever the hardware affords) is invoked only when the shell detects intent that needs tools/planning/reasoning.

This also maps cleanly onto the user's existing T3 MCP pattern: the shell is local and always-on; the cortex is a *provider* that may be local, a cloud model, or another device on the MCP/agent mesh.

---

## 2. Model & component landscape (condensed)

Confidence: findings below are compiled from primary repos/model cards where possible; items marked **[U]** are single-source or unverified and must be re-checked at build time. Model availability and licenses move fast — **re-verify before shipping**.

### 2.1 Native speech-to-speech / full-duplex models

| Model | Params | True duplex? | Latency | Local footprint | Runtime | License |
|---|---|---|---|---|---|---|
| **PersonaPlex-7B** (NVIDIA + Kyutai) | 7B | Yes | ~170–250 ms **[U]** | ~4–5 GB int4 | PyTorch (CUDA + CPU offload) | Code MIT / NVIDIA Open Model weights |
| **Kyutai Moshi** | 7B | Yes (pioneer) | ~160–200 ms | ~4 GB q4 / ~8 GB q8 | PyTorch, **MLX (Mac/iPhone)**, Rust/Candle | CC-BY-4.0 weights (commercial) |
| **MiniCPM-o 4.5** | 9B | Yes + vision | sub-second | ~10 GB int4 | PyTorch, **llama.cpp/Ollama**, vLLM | Apache-2.0 |
| **Nemotron VoiceChat-11B** | 11B | Yes + tool calling | ~450–480 ms | ~22 GB bf16 / quants | vLLM (Linux CUDA) | OpenMDW 1.1 |
| **Qwen3-Omni-30B-A3B** | 30B MoE/3B active | No (turn-based); Realtime variant is closed API | measured ~4.8 s TTFA open **[U]** | ~15–18 GB GGUF | transformers/vLLM | Apache-2.0 |
| **Step-Audio 2 mini** | 8B | No (interruptible, turn-based) | streaming | ~16 GB | vLLM CUDA | Apache-2.0 |
| **GLM-4-Voice** | 9B | No | low-latency decoder | ~10 GB int4 | PyTorch CUDA | Custom GLM license |
| **Ultravox 0.7** | 8B/70B | No (audio-in, **text-out only**) | fast | — | HF/vLLM | MIT |
| **Apple SpeechTranscriber** (STT only) | closed | n/a | ~2.2× Whisper-Turbo on ANE | OS-managed | Apple OS API | Proprietary |

Takeaways:
- **True duplex is real and local at 7–9B**, but the best-duplex models are the weakest at tools/reasoning.
- **Runtime fragmentation is the real gap**: only Moshi has first-class MLX; MiniCPM-o has llama.cpp/Ollama; most others are CUDA/vLLM-only.
- Quantizing audio-codec models tends to hurt output quality more than quantizing text-only LLMs — validate, don't assume.

### 2.2 Cascaded component picks

**STT**

| Option | Strength | Footprint | Runtime | License |
|---|---|---|---|---|
| **Moonshine Streaming** (Tiny/Small/Medium) | truly causal, tiny, MIT, on-device | tens–hundreds MB | ONNX Runtime | MIT |
| **Voxtral Mini 4B Realtime** | natively causal, configurable 80 ms–2.4 s, sweet spot ~480 ms | ~8 GB bf16 | vLLM, ExecuTorch, MLX | Apache-2.0 |
| **NVIDIA Parakeet TDT 0.6B v3** | best accuracy-per-FLOP | ~2.4 GB | NeMo / GGUF C++ | CC-BY-4.0 |
| **whisper.cpp / faster-whisper + distil-large-v3** | compatibility default, mature | 0.4–4 GB | C/C++ / CTranslate2 | MIT |
| **Apple SpeechTranscriber** | free + fast on ANE (Apple only) | OS-managed | OS API | Proprietary |

**TTS**

| Option | Strength | Footprint | License |
|---|---|---|---|
| **Kokoro-82M** | best quality/weight/license, 54 voices | ~300 MB | Apache-2.0 |
| **Supertonic (66M)** | fastest measured (RTF ~0.012 on M4 Pro CPU) | tiny ONNX | OpenRAIL-M |
| **Chatterbox Turbo (350M)** | cloning + emotion, sub-200 ms | ~1–2 GB | MIT (+PerTh watermark) |
| **NeuTTS Air (0.7B)** | on-device zero-shot clone (3 s ref) | ~0.5–1 GB GGUF | Apache-2.0 |
| **Pocket TTS (Kyutai, 100M)** | ~200 ms first audio, CPU-only, cloning | few hundred MB | MIT |
| **Piper** | tiny, CPU realtime, mature | tens of MB/voice | MIT / GPL (successor) |
| **Orpheus-3B** | ~200 ms streaming, emotion tags | ~2 GB q4 | Apache-2.0 |

**VAD / turn detection / AEC**

| Option | Role | Latency | License |
|---|---|---|---|
| **Silero VAD** | frame-level speech gating / barge-in | <1 ms / 30 ms frame | MIT |
| **Pipecat Smart Turn v3.2** (~8M) | semantic end-of-turn (audio-native) | ~10–12 ms CPU | BSD-2 |
| **hierarchical EOT model** (~1.14M) **[U]** | 2026 research; median ~36 ms endpointing, 87.7% recall | ~36 ms | academic |
| **WebRTC AEC3** | echo cancellation for open-speaker barge-in | ~10 ms | BSD-3 |
| **TEN VAD** | efficient NN VAD; beats Silero PR curve | RTF 0.005–0.057 | Apache-2.0 + non-compete |

**Recommended MVP stack:** Silero VAD + WebRTC AEC3 + Smart Turn (endpointing) → Moonshine or whisper.cpp/distil → local Qwen-class 4–8B Q4 with GBNF/JSON-schema tool calls → Kokoro or Supertonic TTS, sentence-streamed.

### 2.3 Runtimes

- **llama.cpp / llama-server** — default engine. Best grammar (GBNF) + JSON-schema tool calling, speculative decoding, prompt/KV cache controls, all platforms.
- **MLX / mlx-lm** — wins on Apple for ≥30B and long context; not ANE; no sub-4-bit.
- **Ollama / LM Studio** — best DX, OpenAI-compatible server; throughput trails raw engines.
- **ONNX Runtime GenAI** — broadest accel matrix incl. NPUs; constrained decoding + tool calls.
- **ExecuTorch** — best Qualcomm NPU path (Android/embedded).
- **vLLM / TensorRT-LLM** — NVIDIA throughput/latency; heavier for desktop.
- **whisper.cpp** — ASR default, incl. Metal/Core ML.

### 2.4 Hardware tiers

Decode is **memory-bandwidth-bound** (~0.1 tok/s per GB/s). Q4_K_M ≈ 0.6 GB per 1B params.

| Tier | Examples | Bandwidth | Max Q4 model | 7B/30B tok/s | Voice viability |
|---|---|---|---|---|---|
| **T0 entry** | Mac Mini M4 16–24 GB, RTX 3060 12 GB, Snapdragon X Elite, phones | 120–135 GB/s | 3–8B | ~28–33 / — | Viable with 3–4B + tiny STT/TTS |
| **T1 mid (sweet spot)** | M4 Pro 24–48 GB, RTX 4090 24 GB / 5080 16 GB | 273 / ~900–1000 GB/s | 14–32B | 48 / 165 (4090); 32B ~45 (4090) | **<500 ms achievable** |
| **T2 high** | M4/M5 Max 64–128 GB, RTX 5090 32 GB, Strix Halo 128 GB | 546–614 / 1792 / 256 GB/s | 32–70B | 91 / 213 (5090); 70B ~12–14 | **Fully viable, ~300 ms** |
| **T3 workstation** | M3 Ultra 96–256 GB, dual 5090 | 800 GB/s | 70B FP16 / 120B+ Q4 | 70B ~12–14 | Works, but 70B decode too slow for natural dialogue |

**Reference build target: T1+ (M4 Pro 24–48 GB or RTX 4090/5080 16–24 GB).**

### 2.5 Quantization

- **Q4_K_M / MLX 4-bit is the realistic realtime floor** (~0.5–2% PPL hit, ~70% size cut). 5-bit is a cheap quality upgrade.
- Sub-3-bit is unsafe except for natively ternary models (BitNet) and hurts **tool-calling reliability first**.
- **KV-cache quantization (q8_0/q4_0)** matters as much as weight quant for long context.

---

## 3. Latency budget (the north star)

Human turn-gap is ~200–300 ms; >400 ms is perceptible; >1.5 s feels like query-response. Streaming everywhere is mandatory.

| Stage | Idle (<300 ms) | Acceptable (<500 ms) | Notes |
|---|---|---|---|
| Capture + AEC + VAD | 20–50 | 50–100 | fixed; overlaps speech |
| End-of-turn decision | 100–200 | 150–250 | **the sleeper cost**; semantic turn detection cuts false interrupts ~45% |
| STT finalize | 50–100 | 100–200 | streaming partials already emitted |
| LLM **TTFT** (prefill) | 100–200 | 200–350 | cache prefix/system prompt; 3–4B ≈ 60–150 ms, 8B ≈ 120–250 ms |
| TTS **TTFB** | 50–150 | 150–300 | sentence-chunked streaming |
| Transport / audio out | 20–50 | 50–100 | local is near-free |
| **Total cascaded** | **~300–450 ms** | **~500–900 ms** | |
| **Full-duplex model** | **~160–250 ms** | — | Moshi/PersonaPlex class |

Two biggest levers: **(1) endpointing** (semantic turn detection can take ~1 s → ~36–60 ms) and **(2) LLM TTFT** (prefix caching, speculative decoding, MoE, small system prompt). Local wins the network-hop term outright.

---

## 4. Recommended architecture: mechanism-neutral, MCP-native, local-first

```
 ┌──────────── ON-DEVICE ───────────────────────────────────────────────────────┐
 │ mic ─▶ AEC3 ─▶ Wake word ─▶ VAD/barge-in (Silero)                            │
 │                                   │ speech                                   │
 │                                   ▼                                          │
 │        ┌───────────────── CONVERSATION SHELL (System 1) ──────────────┐      │
 │        │  • full-duplex model  OR  fast streaming small LLM           │      │
 │        │  • turn-taking, backchannel, interruption, prosody           │      │
 │        │  • emits: speech, intent, barge-in cancels in-flight work    │      │
 │        └───────────────┬───────────────────────────┬───────────────────┘     │
 │                   quick reply                needs tools/reasoning            │
 │                        │                           │                          │
 │                        │                           ▼                          │
 │        ┌───────────────┴────── HARNESS (System 2) ──────────────────────┐     │
 │        │  session state machine · planner/executor · step budget · audit │     │
 │        │  1 fast-path deterministic intents (rules)                     │     │
 │        │  2 CORTEX LLM: local 4–32B, native tool calls + GBNF/JSON      │     │
 │        │  3 router: confidence/risk → stay local | offload              │     │
 │        │  4 policy gate (confirm destructive/spend)                     │     │
 │        │  5 context builder: history + memory + skill index             │     │
 │        └───┬───────────────┬───────────────────┬───────────────┬────────┘     │
 │            │               │                   │               │              │
 │      MCP client mgr    Memory/Skills      Router/Offload   Sandbox/policy     │
 │      (persistent per-  sqlite-vec +      LiteLLM/OpenAI-   containers,       │
 │       server, stdio    SQLite; skill://  compatible →      default-deny FS,   │
 │       local / HTTP     progressive       Claude/GPT/       egress allowlist,  │
 │       remote, cached)  disclosure        Gemini or 2nd     quotas, timeouts   │
 │            │                             device (text-only, redacted)         │
 │            ▼                                                                   │
 │      local MCP servers: filesystem, sqlite, browser, shell, HA, calendar       │
 │            │ tool result (UNTRUSTED)                                           │
 │            └──▶ validate + sanitize + redact + cap ──▶ back to cortex          │
 │                                   │ response text                             │
 │                                   ▼                                            │
 │              TTS (Kokoro/Supertonic/Chatterbox) sentence-streamed ─▶ speaker   │
 │                                                                                │
 │  cross-cutting: audit log · security telemetry · eval/regression suite         │
 └────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 The split-brain idea (the key design choice)

Model the agent on System 1 / System 2:

- **System 1 — Conversation Shell.** Small, always-listening, extremely low latency. Owns *feel*: turn-taking, backchannel ("mm-hm", "got it"), barge-in, prosody, quick answers. Can be a full-duplex model (Moshi/PersonaPlex) or a 1–4B streaming LLM on a cascade. It has a tiny tool surface: essentially "answer directly" or "hand to cortex."
- **System 2 — Cortex.** 4–32B local tool-caller (or offloaded). Invoked by intent. Owns *correctness*: tool calls, plans, RAG, multi-step. Latency is acceptable here because the shell covers it with natural backchannel.

This is the single most important architectural decision and it is what makes a local Jarvis feel good without pretending a 7B can beat a frontier model at everything.

### 4.2 Streaming and cancellation contract

Everything streams and everything cancels:
- Audio frames → VAD → partial transcripts continuously.
- Cortex streams tokens; TTS begins on the first complete clause, not the full response.
- **Barge-in cancels TTS playback, the in-flight LLM generation, and in-flight tool calls** (MCP: `notifications/cancelled` over stdio; close the stream over HTTP). Cancellation must be end-to-end, not just audio.

---

## 5. MCP integration specifics (2026-07-28 spec)

- **Transports:** `stdio` is the default and correct choice for local servers (client launches the process). Streamable HTTP is now **stateless**, suitable for remote/offloaded servers. Legacy HTTP+SSE is deprecated.
- **Primitives:** Tools (`tools/list`, `tools/call`, JSON Schema in/out, `structuredContent`), Resources (context/data), Prompts (templates).
- **Elicitation / MRTR** — the mechanism for in-call confirmation ("delete these 12 files?") via `input_required` + `inputResponses`. This is how the policy gate talks to the user.
- **Extensions:** **Tasks** (async, durable, pollable — for long/offloaded jobs) and **Skills over MCP** (`skill://`, progressive disclosure via `skill://index.json`).
- **Caching:** list results are cacheable; tool catalogs should be cached and advertised selectively (progressive tool discovery) to keep the small model's context small.
- **Auth:** OAuth 2.1 + PKCE for remote servers; local stdio usually none.

**Harness rules:**
1. One persistent MCP client per server; list tools once; namespace tools; cache.
2. Advertise a *small* entry-point tool set; reveal more on demand (progressive discovery) — critical for 4–8B context.
3. Validate tool args against JSON Schema; on `isError`, feed the error back and retry within a step budget.
4. **Tool output is untrusted.** Validate against `outputSchema`, sanitize/redact, cap size, and never treat it as instructions (prompt-injection defense).
5. Offload **text only**, redacted and task-scoped, through a LiteLLM/OpenAI-compatible gateway. Disclose cloud use.
6. Long jobs → MCP **Tasks**; continue locally.

This maps directly onto the user's T3 MCP mesh: the on-device harness is just another MCP-capable node, and the "cortex" can be a remote/other-device provider behind the router.

---

## 6. Security (do not defer this)

An always-on local agent with shell/filesystem/browser MCP servers is an RCE-shaped target and history is not kind (cf. OpenClaw: RCE CVE, tens of thousands of exposed instances, malicious skills).

- **Default-deny** filesystem and network egress; explicit allowlists; per-server scoping.
- **Sandbox** tool execution (container/microVM or macOS `sandbox-exec`; Docker MCP Gateway pattern) with CPU/mem quotas and hard timeouts.
- **Confirm** destructive or spend-triggering actions via elicitation; never auto-run shell from model output.
- **Treat all tool output as untrusted input** (indirect prompt injection); datamark/spotlight it.
- **Audit log** every tool call + args + result hash; keep security telemetry.
- Wake-word gating + a visible "listening" indicator; easy global mute.
- Voice cloning: use MIT/Apache weights only for commercial (Chatterbox, Kokoro, Orpheus, Piper, Moshi); never clone third-party voices without consent; watermark + disclose synthetics (XTTS-v2 is CPML non-commercial; F5-TTS is CC-BY-NC).

---

## 7. Innovation opportunities (push the boundary)

Beyond a straight implementation, these are worth prototyping because they are where a local-first design can *beat* the cloud UX:

1. **Speculative backchannel.** While the cortex works, the shell generates context-appropriate acknowledgements ("right", "let me check that") from a tiny model. Perceived latency drops even when real latency doesn't.
2. **Duplex front-end + tool cortex handoff.** Train/prompt the duplex shell to emit a structured "handoff" token when it detects a tool-shaped intent, keeping conversation natural while delegation happens.
3. **Predictive prefill / prompt cache pinning.** Cache the system prompt, tool catalog, and rolling context so cortex TTFT is near-zero on the second turn.
4. **Speculative tool calls.** For high-confidence intents, speculatively execute a read-only tool while the cortex is still decoding; discard if the plan diverges.
5. **Local mesh offload.** The user's T3 MCP pattern generalized: route a heavy sub-task to another device on the LAN running a bigger model, keeping audio local. This is a genuine differentiator — a personal compute mesh instead of a cloud tenant.
6. **Voice-native skill discovery.** Use Skills-over-MCP progressive disclosure so the model only sees skills relevant to the current utterance, shrinking prompts and speeding prefill.
7. **On-device eval harness.** A deterministic suite of voice/tool scenarios (like the local tool-calling evals) that runs on every model/quant change — essential because quant and chat-template drift silently break tool calling.

---

## 8. Phased build plan

**Phase 0 — Harness spike (no voice).** Prove the local tool loop.
- Components: llama.cpp/Ollama + a 4B tool-trained model (Qwen3.5-4B / Nemotron-Nano-4B class) + MCP stdio client + 2–3 local MCP servers (filesystem read-only, sqlite, HTTP fetch).
- Deliverable: text CLI that routes fast-path vs cortex, validates tool args, handles `isError`, enforces permissions.
- Exit criteria: ≥95% pass on a 40-case deterministic tool eval; audited, sandboxed tool execution.

**Phase 1 — Cascaded voice loop.** Make it speak and listen.
- Components: Silero VAD + AEC3 + Smart Turn → whisper.cpp/Moonshine STT → Phase-0 cortex → Kokoro/Supertonic TTS, sentence-streamed.
- Deliverable: push-to-talk, then hands-free with barge-in.
- Exit criteria: measurable end-to-end voice-to-voice p50 <700 ms on T1 hardware; barge-in cancels audio + LLM + tools.

**Phase 2 — Duplex shell + split-brain.**
- Add Moshi/PersonaPlex (Mac MLX first) as the conversation shell; route to the cortex on intent. Backchannel + speculative speech.
- Exit criteria: natural interruption; perceived latency clearly better than Phase 1; shell never blocks tool execution.

**Phase 3 — Memory, skills, offload.**
- sqlite-vec memory, Skills-over-MCP, MCP Tasks for long jobs, router for cloud/second-device offload, voice cloning with watermarks.
- Exit criteria: multi-turn personal context; explicit, disclosed offload with redaction.

**Phase 4 — Platform hardening & packaging.**
- Cross-platform runtimes (MLX/CUDA/ONNX), mobile tier, eval harness in CI, signed/permissioned install, telemetry + audit UI.

**Proposed repo layout (scaffold created):**

```
local-jarvis/
  docs/
    research/2026-09-local-voice-jarvis.md
    architecture/
      adr/0001-split-brain-architecture.md
  packages/            # to be created when implementation starts
    core/              # session state machine, events, cancellation
    audio/             # capture, AEC, VAD, turn detection, playback
    stt/               # whisper.cpp / Moonshine adapters
    tts/               # Kokoro / Supertonic adapters
    llm/               # llama.cpp / MLX / Ollama / remote providers
    mcp/               # MCP client manager, tool registry, policy gate
    router/            # local vs offload, confidence/risk gating
    memory/            # sqlite-vec, episodic store
    eval/              # deterministic voice + tool evals
  apps/
    cli/               # Phase 0 text harness
    desktop/           # Phase 1+ voice app
```

---

## 9. Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Small-model tool-calling reliability (compounding errors: 95%^8 ≈ 66%) | High | Short horizons, planner/executor split, schema validation + retry, fast-path deterministic intents, offload escalation on low confidence |
| Quantization silently breaks tool calls | High | On-device eval on every quant/template change; Q4_K_M floor; test in the *exact* runtime |
| Endpointing latency dominates UX | High | Semantic turn detection (Smart Turn / hierarchical EOT); tune stop thresholds; speculative backchannel |
| Runtime fragmentation (MLX vs CUDA vs NPU) | Medium | Abstract behind an LLM/STT/TTS provider interface from day one; ship one platform first (Apple Silicon) |
| Audio-codec models degrade under quantization | Medium | Validate per model; prefer fp16/q8 for the codec, quantize only the LLM |
| Security / prompt injection / RCE | Critical | Default-deny sandbox, permission gates, untrusted-output handling, audit, no auto-shell |
| Licensing (XTTS CPML, F5 CC-BY-NC, GLM custom) | Medium | Curate a permissive-first model allowlist; watermark + consent + disclosure |
| Hardware gap at the low tier | Medium | Explicit tier matrix; T0 ships reduced (3–4B, text-first, fewer tools) |
| Verification: some 2026 model names/benchmarks are single-source | Medium | Re-verify every model card, size, and license at build time (see confidence note) |

---

## 10. Open decisions (need user direction)

1. **Primary path:** cascaded-first (reliable, tool-rich) vs duplex-first (best feel). *Recommendation: cascaded-first, duplex as Phase 2.*
2. **Primary platform:** Apple Silicon (M4 Pro+ / MLX) vs NVIDIA (RTX 40/50 + CUDA). *Recommendation: Apple Silicon reference build, CUDA second.*
3. **How local is "local"?** Is any cloud offload acceptable (with disclosure), or must v1 be 100% on-device? This changes the model strategy materially.
4. **Relationship to T3 MCP:** does the on-device harness become another T3 node/provider, or is it standalone? *Recommendation: MCP-native so it can join the existing mesh.*
5. **Voice cloning in v1 or later?** It increases privacy/consent/compute risk.

---

## Appendix — Confidence & verification note

This report compiles primary sources (repos, model cards, MCP spec) and 2025–2026 secondary analyses. The area moves fast and several specific claims are single-sourced. Treat the following as **must re-verify at build time**: exact quantized footprints and latency numbers for 2026 duplex models (PersonaPlex, Nemotron VoiceChat, MiniCPM-o 4.5); Apple M5 Pro/Max bandwidth; compressed tool-calling benchmark numbers; specific MCP extension statuses (Tasks/Skills); and every model license. The *architecture* recommendation (split-brain, MCP-native, local-first, streaming-everywhere, evaluate-every-change) is robust to these uncertainties; the *specific model picks* are not.

**Primary sources consulted include:** Kyutai Moshi (github.com/kyutai-labs/moshi), NVIDIA PersonaPlex, OpenBMB MiniCPM-V/o, NVIDIA NeMo VoiceChat, Qwen3-Omni, Mistral Voxtral Realtime, Moonshine, NVIDIA Parakeet TDT, whisper.cpp/faster-whisper, Kokoro-82M, Supertonic, Chatterbox, NeuTTS Air, Kyutai Pocket TTS, Silero VAD, Pipecat Smart Turn, TEN VAD, llama.cpp (GBNF + server + speculative), MLX, ONNX Runtime GenAI, ExecuTorch, MCP spec 2026-07-28 (modelcontextprotocol.io), Pipecat / LiveKit Agents / Home Assistant Assist / Goose / Open Interpreter prior art, and the 2026 on-device TTS and local tool-calling benchmark write-ups.
