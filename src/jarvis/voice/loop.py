from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from jarvis.audio.capture import Microphone
from jarvis.audio.playback import Speaker
from jarvis.audio.vad import VadSegmenter
from jarvis.core.events import CancelToken, CancelledError, EventBus
from jarvis.harness.loop import AgentHarness
from jarvis.stt.base import STT
from jarvis.tts.base import TTS, to_speech_text


@dataclass
class VoiceConfig:
    input_device: Optional[int] = None
    output_device: Optional[int] = None
    sample_rate: int = 16000
    frame_ms: int = 30
    vad_aggressiveness: int = 2
    end_silence_ms: int = 700
    max_utterance_s: float = 30.0
    barge_in: bool = True
    stt_model: str = "base.en"
    tts_voice: str = "af_sarah"
    speech_speed: float = 1.0
    greeting: str = ""


class VoiceLoop:
    """Mic -> VAD -> STT -> harness -> TTS -> speaker, with barge-in.

    One `CancelToken` per turn is shared by the LLM call and TTS playback, so a
    barge-in stops the agent mid-sentence and mid-thought.
    """

    def __init__(
        self,
        harness: AgentHarness,
        stt: STT,
        tts: TTS,
        *,
        mic: Optional[Microphone] = None,
        speaker: Optional[Speaker] = None,
        config: Optional[VoiceConfig] = None,
        bus: Optional[EventBus] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.harness = harness
        self.stt = stt
        self.tts = tts
        self.config = config or VoiceConfig()
        self.bus = bus or EventBus()
        self.log = log or (lambda msg: print(msg))
        self.mic = mic or Microphone(
            sample_rate=self.config.sample_rate,
            frame_ms=self.config.frame_ms,
            device=self.config.input_device,
        )
        self.speaker = speaker or Speaker(device=self.config.output_device)
        self._segmenter = VadSegmenter(
            sample_rate=self.config.sample_rate,
            frame_ms=self.config.frame_ms,
            aggressiveness=self.config.vad_aggressiveness,
            end_silence_ms=self.config.end_silence_ms,
            max_speech_s=self.config.max_utterance_s,
        )
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._turn_lock = asyncio.Lock()
        self._active_cancel: Optional[CancelToken] = None
        self._turn_task: Optional[asyncio.Task] = None

    # -- lifecycle -----------------------------------------------------------

    async def run(self) -> None:
        loop = asyncio.get_running_loop()

        def on_frame(frame: np.ndarray) -> None:
            loop.call_soon_threadsafe(self._queue.put_nowait, frame)

        await self.harness.start()
        try:
            self.mic.start(on_frame)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"could not open the microphone ({e}). Check macOS System Settings > "
                "Privacy & Security > Microphone, and your input device."
            ) from e
        self.log("Jarvis listening. Speak, then pause. Ctrl-C to stop.")
        try:
            if self.config.greeting:
                await self._respond(self.config.greeting)
            while not self._stop.is_set():
                frame = await self._queue.get()
                await self._on_frame(frame)
        finally:
            self.mic.stop()
            await self.harness.stop()

    def request_stop(self) -> None:
        self._stop.set()
        if self._active_cancel:
            self._active_cancel.cancel()

    # -- audio pump ----------------------------------------------------------

    async def _on_frame(self, frame: np.ndarray) -> None:
        utterance = self._segmenter.push(frame)
        if (
            self.config.barge_in
            and self._segmenter.just_started
            and self._active_cancel is not None
            and not self._active_cancel.cancelled
        ):
            await self.bus.publish("barge_in", {})
            self.log("  (barge-in — stopping)")
            self._active_cancel.cancel()
        if utterance is not None:
            if not self.config.barge_in and self._turn_task is not None and not self._turn_task.done():
                self.log("  (still speaking; utterance ignored)")
                return
            self._turn_task = asyncio.create_task(self._handle_utterance(utterance))

    async def _handle_utterance(self, utterance: np.ndarray) -> None:
        async with self._turn_lock:
            text = (await asyncio.to_thread(self.stt.transcribe, utterance, self.config.sample_rate)).strip()
            if not text:
                return
            self.log(f"you> {text}")
            await self._respond(text)
            self.log("")

    async def _respond(self, text: str) -> None:
        """Run one turn and speak the reply. Shared cancellation covers both."""
        token = CancelToken()
        self._active_cancel = token
        try:
            result = await self.harness.run(text, cancel=token)
            if result.cancelled or token.cancelled:
                return
            reply = result.text.strip()
            if not reply:
                return
            self.log(f"jarvis> {reply}")
            await self.bus.publish("assistant", {"text": reply})
            spoken = to_speech_text(reply)
            if not spoken:
                return
            for chunk in self.tts.synthesize_stream(
                spoken, voice=self.config.tts_voice, speed=self.config.speech_speed
            ):
                if token.cancelled:
                    break
                if chunk is None or len(chunk) == 0:
                    continue
                finished = await asyncio.to_thread(
                    self.speaker.play, chunk, self.tts.sample_rate, cancel=token
                )
                if not finished:
                    break
        except CancelledError:
            pass
        finally:
            self._active_cancel = None
