# Design references

Visual source of truth for the simple UI, from Alex's T3 task *"Futuristic Voice
Agent Widget UI"* (environment `desktop-pc`). The three source images are preserved here:

- `simple-light-popover.png` — hero mic card (light) with Chat / Keyboard / Settings.
- `simple-widget-states.png` — collapsed mic, expanded caret popover, text-input popover.
- `simple-dark-widget.png` — dark card with a status line ("Ready").

Direction: **flat, minimal, light/dark tray popovers.** A single microphone button with
only essential Chat, Keyboard, and Settings controls; collapsed/expanded/text-entry
states; a text field when Keyboard is selected. Rejected: cinematic hardware, glass,
glow, orbs, rings, waveform visuals.

## Implemented states (screenshots)

Captured from the served page (headless Chromium via `playwright-cli`):

- `ui-menu-light.png` — expanded caret popover (matches the expanded state / light popover).
- `ui-menu-dark.png` — dark card with the `Ready` status line.
- `ui-input-light.png` — text-input popover ("Type a message…").
- `ui-chat-light.png` — conversation view.
- `ui-settings-light.png` — concise settings.
- `ui-listening-light.png` — collapsed, active (solid blue) mic.

Preview hooks make these reproducible: `/?view=menu|chat|input|settings&theme=light|dark&state=listening`.

## Intentional deltas from the stills

- The stills show two light layouts (a hero card and caret popovers). We implemented the
  **caret-popover interaction model** from `simple-widget-states.png` (it is the one that
  maps to real states).
- The dark still places labels in pills above circular icon buttons; we use label rows
  (matching the expanded state) for one consistent control treatment.
- Added a **Send** button beside the text field (the still shows the field only) for
  keyboard usability.

## Attribution

Source images are Alex's design work produced for this project; kept here as design
references. Reuse outside this project should credit the author.
