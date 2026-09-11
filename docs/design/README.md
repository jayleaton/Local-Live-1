# Design references

Visual source of truth for the simple UI. The three latest images from Alex's T3 task
*"Futuristic Voice Agent Widget UI"* (environment `desktop-pc`) are expected here:

- `simple-light-popover.png`
- `simple-widget-states.png`
- `simple-dark-widget.png`

**Status: pending transfer.** Direct push from the Windows host failed (SSH/SMB/AFP
unreachable from there) and there is no public file server by design. Proposed routes:
an SMB share/credentials the Mac can *pull* from `home-desk:445`, Taildrop, or a private
gist/artifact URL. Do not claim the UI matches these images until they are present and
reviewed.

## Direction (from the task text, not yet visually verified)

Flat, minimal, light/dark tray popovers. A single microphone button with only essential
chat, keyboard, and settings controls. Collapsed/expanded/text-entry states; a text field
appears when Keyboard is selected. Explicitly **rejected**: cinematic hardware, glass,
glow, orbs, rings, and waveform visuals.
