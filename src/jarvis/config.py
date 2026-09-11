from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from jarvis.mcp.manager import ServerConfig
from jarvis.policy.gate import PolicyGate


@dataclass
class ModelConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    api_key: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout: float = 120.0
    temperature: float = 0.3
    max_tokens: int = 1024
    # Provider-specific request-body params, e.g. {"thinking": {"type": "disabled"}}.
    extra_params: dict = field(default_factory=dict)
    reasoning_effort: Optional[str] = None
    strict_tools: bool = False

    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


@dataclass
class PolicyConfig:
    allowed_servers: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)
    read_only_only: bool = False
    auto_approve: bool = False


@dataclass
class HarnessSettings:
    max_steps: int = 6
    history_turns: int = 12
    max_tool_result_chars: int = 16000


@dataclass
class VoiceSettings:
    stt_model: str = "base.en"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    tts_voice: str = "af_heart"
    tts_backend: str = "chatterbox"  # chatterbox | kokoro
    speech_speed: float = 1.0
    barge_in: bool = True
    end_silence_ms: int = 700
    vad_aggressiveness: int = 2
    input_device: Optional[int] = None
    output_device: Optional[int] = None
    greeting: str = ""
    streaming: bool = True
    streaming_backend: str = "nemotron"  # nemotron | sherpa
    nemo_url: str = "ws://127.0.0.1:8081"
    nemo_model: str = "nemotron-3.5"
    endpointing_ms: int = 1500
    max_spoken_sentences: int = 3
    streaming_ws_port: Optional[int] = None


@dataclass
class LocalModelConfig:
    """On-device conversational shell that produces the spoken replies."""

    provider: str = "mlx"
    model: str = "mlx-community/Qwen2.5-3B-Instruct-4bit"
    temperature: float = 0.4
    max_tokens: int = 256


@dataclass
class AgentConfig:
    """A higher-skilled worker agent the dispatcher can invoke.

    Backed by any OpenAI-compatible endpoint (DeepSeek, a coding-agent gateway,
    etc.). The working agent returns text; the local model relays it to the user.
    """

    name: str = "worker"
    description: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    api_key: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    system_prompt: str = (
        "You are a highly skilled worker agent. Complete the task fully and return "
        "a concise, actionable result that can be read aloud to the user."
    )
    temperature: float = 0.2
    max_tokens: int = 4096
    reasoning_effort: Optional[str] = "high"
    extra_params: dict = field(default_factory=dict)
    timeout: float = 300.0
    strict_tools: bool = False

    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


@dataclass
class DispatchSettings:
    enabled: bool = True
    patterns: list[str] = field(default_factory=list)
    local_patterns: list[str] = field(default_factory=list)
    max_tasks: int = 1


@dataclass
class JarvisConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    local: Optional[LocalModelConfig] = None
    response_mode: str = "local"  # local | api
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    settings: HarnessSettings = field(default_factory=HarnessSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    dispatch: DispatchSettings = field(default_factory=DispatchSettings)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    servers: dict[str, ServerConfig] = field(default_factory=dict)
    # Where this config was loaded from, so runtime changes persist back there.
    source_path: Optional[str] = None

    @staticmethod
    def load(path: str | Path) -> "JarvisConfig":
        data = json.loads(Path(path).read_text())
        cfg = JarvisConfig.from_dict(data)
        cfg.source_path = str(path)
        return cfg

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "JarvisConfig":
        model = ModelConfig(**{k: v for k, v in (data.get("model") or {}).items() if k in ModelConfig.__dataclass_fields__})
        policy = PolicyConfig(
            **{k: v for k, v in (data.get("policy") or {}).items() if k in PolicyConfig.__dataclass_fields__}
        )
        settings = HarnessSettings(
            **{k: v for k, v in (data.get("settings") or {}).items() if k in HarnessSettings.__dataclass_fields__}
        )
        voice = VoiceSettings(
            **{k: v for k, v in (data.get("voice") or {}).items() if k in VoiceSettings.__dataclass_fields__}
        )
        local = None
        if data.get("local"):
            local = LocalModelConfig(
                **{k: v for k, v in data["local"].items() if k in LocalModelConfig.__dataclass_fields__}
            )
        dispatch = DispatchSettings(
            **{k: v for k, v in (data.get("dispatch") or {}).items() if k in DispatchSettings.__dataclass_fields__}
        )
        agents = {
            name: AgentConfig(
                name=name,
                **{k: v for k, v in (cfg or {}).items() if k in AgentConfig.__dataclass_fields__ and k != "name"},
            )
            for name, cfg in (data.get("agents") or {}).items()
        }
        servers = {
            name: ServerConfig(
                name=name,
                command=list(cfg.get("command", [])),
                url=cfg.get("url", ""),
                headers={k: os.path.expandvars(v) for k, v in (cfg.get("headers") or {}).items()},
                env=cfg.get("env", {}),
                cwd=cfg.get("cwd"),
                enabled=cfg.get("enabled", True),
                allow=cfg.get("allow", []),
                deny=cfg.get("deny", []),
                request_timeout=cfg.get("request_timeout", 30.0),
            )
            for name, cfg in (data.get("servers") or {}).items()
        }
        return JarvisConfig(
            model=model,
            local=local,
            response_mode=data.get("response_mode", "local"),
            policy=policy,
            settings=settings,
            voice=voice,
            dispatch=dispatch,
            agents=agents,
            servers=servers,
        )

    def build_gate(self, confirmer=None) -> PolicyGate:
        return PolicyGate(
            allowed_servers=self.policy.allowed_servers or None,
            deny_patterns=self.policy.deny_patterns,
            read_only_only=self.policy.read_only_only,
            auto_approve=self.policy.auto_approve,
            confirmer=confirmer,
        )
