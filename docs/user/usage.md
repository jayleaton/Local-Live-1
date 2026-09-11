# Using Jarvis

Jarvis runs on your host machine and is used from a browser or the desktop app.

## Talk to it

1. Open the Jarvis UI (locally `http://127.0.0.1:8766`, or `https://<machine>.<tailnet>.ts.net:8443` over Tailscale).
2. Press the microphone button and speak. When you pause, it finalizes automatically —
   there is no stop button to press.
3. It shows the state: **listening → thinking → speaking**. Start talking again at any time
   to interrupt (barge-in).

The page must be served over HTTPS (or localhost) for the microphone to work — browsers
require a secure context. Over Tailscale this is handled by `tailscale serve`.

## Type instead

Toggle the keyboard control to open a text field and send a message without speaking.

## Controls

- **Microphone** — start/stop listening.
- **Keyboard** — show/hide the text field.
- **History** — view the conversation.
- **Settings** — choose the response brain (on-device or API), the on-device model, the
  TTS engine/voice, and how many sentences are spoken aloud. Nothing advanced is required.

## Settings you may care about

- **Response brain** — *Local* keeps replies on-device; *API* uses a remote model. Voice
  processing stays on the host either way.
- **Speech recognition** — choose the speech-to-text model. *Sherpa Zipformer* is built in
  and runs offline with no download. *NVIDIA Nemotron streaming* models are more accurate:
  selecting one installs the NVIDIA runtime (first time, opt-in) and downloads the model,
  showing progress in Settings. The active model is shown under the selector.
- **Max spoken sentences** — caps how much of the reply is read aloud (the full text still
  appears on screen). Useful for long answers.
- **TTS engine** — *Chatterbox* sounds more natural; *Kokoro* is faster.

## Privacy

Audio, speech models, and (by default) the language model run on the host. A remote model
is only used if you select the API brain or a tool/worker agent explicitly calls out.
