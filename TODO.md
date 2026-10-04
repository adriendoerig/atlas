# Next steps (deliberately outside Phase A/B)

1. Backend auto-start from M4L: a node.script helper should check localhost for
   the expected Drum Atlas service, launch the configured project-local
   `.venv/bin/drum-atlas serve` when absent, wait for readiness, then load jweb~.
   Prevent duplicate launches, handle occupied ports, and record logs outside
   the source tree. Device unload should not stop a backend used by other devices.
2. Installation on another Mac: choose and provision a supported Python/runtime,
   recreate dependencies (do not copy this machine's virtualenv), download or
   reuse licensed model weights, and let the user choose sample folders.
   Libraries reference local absolute paths, so audio paths need reconciliation.
3. Only after those are stable: signed/notarized .app or installer, architecture
   testing, model/license notices, versioned upgrade/rollback and uninstall flows.
4. Product improvements: native folder selection, richer manual curation UI,
   durable scan jobs with progress/cancellation, cross-process scan locking, and
   scalable neighbor search/rendering for large libraries.

No .app, installer, or M4L auto-launch patch was built in this update.
