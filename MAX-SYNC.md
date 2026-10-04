# Max for Live subdivision wiring

The browser and Live page now offer one Audition timing menu:

| Menu | Max messages |
| --- | --- |
| 1-shot | `scrubsync 0`; one-shot selection throttled to 90 ms |
| 16ths | `scrubdivision 16n`, then `scrubsync 1` |
| 8ths | `scrubdivision 8n`, then `scrubsync 1` |
| 4ths | `scrubdivision 4n`, then `scrubsync 1` |

`selected <id> <path>` still loads the current sound. `scrub 1` arms the clock
while dragging; `scrub 0` stops it on release. Changing timing while dragging
stops the previous gesture before changing the subdivision. 1-shot never arms
the repeating clock. Clicking and Replay retain the existing one-shot behavior.
The timing menu synchronizes in both directions and reconnect state includes it.
Without Live, audition remains ordinary one-shot playback; the browser does not
invent a separate BPM clock.

## Patch change

Add **scrubdivision** as a new selector at the *end* of your existing `route`
object, preserving the outlet order of its existing selectors. Take that new
outlet (which receives `16n`, `8n`, or `4n`) and feed two branches:

- `[prepend interval]` → left inlet of your existing `[metro 16n @quantize 16n]`.
- `[prepend quantize]` → the same left inlet.

Keep the existing `scrubsync`/`scrub` gate and sample-retrigger wiring. Live's
transport must run for tempo-relative scheduling. Reload jweb~ after making the
change so the current timing is sent again. Until the new branch is wired,
16ths and 1-shot retain the previous behavior, while 8ths/4ths cannot change the
Max clock. No `.amxd` has been modified or bundled by this update.

The interval and quantize attributes accept note values according to the
[official metro reference](https://docs.cycling74.com/reference/metro/).

## Backend protocol

Send `{ "type":"scrub_mode", "mode":"one-shot" }` (or `16n`, `8n`, `4n`) to
`/api/sync`. Unknown values are ignored. Initial state contains `scrub_mode`,
`scrub_sync` (the legacy boolean), and `scrub_active`.
Legacy `scrub_sync` messages still work: enabling from one-shot selects 16ths;
disabling selects one-shot. Scrub-active requests are ignored while in one-shot.
