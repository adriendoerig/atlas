# Drum Atlas working agreements

The user made and committed performance fixes in 5f06094. Preserve these when
editing, and start from the actual project rather than older Work staging copies:
- Latest-selection-wins audio loading with cancellation of stale requests.
- Option-click explicitly requests neighbors; ordinary clicks/drags do not.
- Incremental list selection updates and the user's map/neighbor caching.
- Actual MaxBridge heartbeats plus Ableton-process checks control Live presence.
- Launch.command exports the source folder on PYTHONPATH so source edits are used.

Keep pool combinations, subset projections, adaptive dot sizes, Live-safe wheel
behavior, and compact layout working. Timing modes must synchronize across views;
1-shot must never leave Max's repeating clock armed. Subdivision wiring is documented
in MAX-SYNC.md; do not claim Max audio-clock testing without actually doing it.

The user prefers efficient work and meaningful tests at the end rather than
repeated full-suite runs. Deployment on other machines is currently a macOS
source setup bundle. Never include this user's audio, database, venv, or model
cache in a distribution archive.
