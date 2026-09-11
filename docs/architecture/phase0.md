# Phase 0 — Text Tool Harness

Goal: prove the hard part (the agent harness around local models + MCP) before adding any audio.

## What it does

A single turn flows through:

1. **Router** — checks deterministic **fast-path** rules first (e.g. "what time is it" → `now` tool). Fast paths are the lowest-latency, highest-reliability route and bypass the cortex LLM.
2. **Cortex loop** — otherwise the LLM is called with the advertised tool catalog. Tool calls are authorized by the **PolicyGate**, executed against the **ToolRuntime** (MCP servers), and results are fed back. Loops up to `max_steps`, feeding errors back for self-correction.
3. **Untrusted output handling** — every tool result is wrapped and explicitly marked as data, truncated, and never treated as instructions.
4. **Cancellation** — one `CancelToken` propagates from barge-in through LLM generation and in-flight MCP calls (`notifications/cancelled`).

## Interfaces (the seams that matter)

```python
class ToolRuntime(Protocol):            # MCPClientManager (prod) | InMemoryToolRuntime (test/eval)
    async def start() -> None
    async def stop() -> None
    def tools() -> list[ToolSpec]
    async def call(name, arguments, *, cancel=None) -> ToolResult

class LLMProvider(ABC):                 # OpenAICompatProvider | ScriptedProvider
    async def complete(messages, tools, *, temperature, max_tokens, cancel) -> LLMResponse

class PolicyGate:
    def check(call, spec) -> PolicyDecision
    async def authorize(call, spec) -> PolicyDecision   # runs the confirmer if needed
```

Everything else (voice shell, STT, TTS, memory, offload) attaches behind these seams.

## MCP details implemented

- `initialize` / `notifications/initialized` handshake, protocol version negotiation.
- `tools/list` with cursor pagination; `tools/call`; `notifications/cancelled`.
- Server→client requests (`ping`, `roots/list`) answered; unknown methods return JSON-RPC `-32601`.
- Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) → policy hints.
- One persistent client per server; a failing server is isolated (recorded in `manager.errors`, others still work).

## Eval suite (13 deterministic cases)

`direct_answer`, `single_read_tool`, `tool_error_then_recover`, `destructive_denied_without_confirmer`, `destructive_confirmed`, `read_only_mode_blocks_write`, `deny_pattern_blocks`, `fast_path_time`, `step_budget_exceeded`, `unknown_tool_denied`, `cancel_before_run`, `cancel_during_tool`, `history_retained_across_turns`.

Run with `uv run python -m jarvis eval`. These are the regression baseline for every future model/quant change.

## Deliberate non-goals (deferred)

- Streaming token/audio output (interface is ready; implementation is Phase 1).
- Anthropic-native message format (add a provider; the seam is OpenAI-shaped).
- Streamable HTTP MCP transport (only stdio in Phase 0).
- Memory/embeddings, skills, Tasks (Phase 3).
- Voice (Phase 1+).

## Next (Phase 1)

VAD + AEC + turn detection → streaming STT → this cortex → streaming TTS, with end-to-end barge-in. See the research doc §8.
