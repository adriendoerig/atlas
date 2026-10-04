# Drum Atlas — V0

A local sample browser with a compact Max for Live web view, synchronized audition controls, and reusable sample pools.

## Run

On this Mac, the permanent project is `/Users/adriendoerig/Documents/DrumAtlas`.
Double-click `Launch.command` there, or run:

```sh
cd /Users/adriendoerig/Documents/DrumAtlas
.venv/bin/drum-atlas serve
```

Open http://127.0.0.1:8765. In Max, keep the existing URL
`http://127.0.0.1:8765/?view=live`. Reload the web view after updating the server.
Only one server can occupy port 8765. Stop it with Ctrl-C in its launching terminal
before starting another copy. The launcher uses only the project-local `.venv`.

Persistent locations on macOS:

- Database, pool definitions, active pool selection: `~/Library/Application Support/Drum Atlas/library.sqlite`.
- Model weights and compiled analysis cache: `~/Library/Caches/Drum Atlas/`.
- Original sample audio stays in its existing folders; nothing copies or moves that audio.

`drum_atlas/paths.py` defines these defaults. Set `DRUM_ATLAS_DATA_DIR` or
`DRUM_ATLAS_CACHE_DIR` to override the directories. `--db` remains available before
any command; `scan --model-cache` overrides the model cache independently:

```sh
.venv/bin/drum-atlas --db /path/to/library.sqlite serve --port 8767
```

The local environment has its own installed dependencies and no dependency on the
old Work virtualenv. Like a normal Python virtualenv, it still uses the Python
3.12 installation with which it was created. It is a development environment, not
a redistributable runtime. To recreate it with your own Python 3.12 installation:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install '.[test]'
```

After editing Python source, reinstall it with `.venv/bin/python -m pip install --no-deps --no-build-isolation .`.
The project uses a regular install so console launches do not depend on editable-install discovery.

The existing pinned CLAP model cache was copied. A fresh installation downloads
`laion/clap-htsat-unfused` on its first normal scan; inference then runs locally.
Audio is never uploaded.

## Sample pools

Expand **Sample pools** in the full browser. Check any combination of pools to
show their distinct union. Unchecking every pool gives an empty view. A sample
that belongs to two checked pools appears once. Counts include rejected and
unembedded files; the map shows the accepted subset.

Use **+ New Pool**, enter a name and an absolute folder path, then **Create and
scan**. The folder is scanned recursively. **Rescan** updates its membership and
analyses only changed, outdated, or new files. Known eligible CLAP embeddings are
reused. **Delete** removes the pool references, retaining global analysis and
original audio. If a scan fails, the saved pool remains available for retry.

The original 383 samples were migrated into **Polaroit**. Your **Artist kicks**
pool (449 samples) is also preserved. The library now contains 832 samples,
588 of which pass the current mapping filters.

Pool selection is persisted and synchronized to all browser/Live views. Pool
management is hidden in the tiny Live layout. Both projections remain global:
selection only hides points, keeping the same coordinates, scale, and global
feature normalization. Scanning genuinely new/changed content can rebuild the
global map. Nearest-neighbor results use full-dimensional vectors and are limited
to the active union.

The schema supports both folder and manual pools. Manual curation currently uses
the API (see `ARCHITECTURE.md`); the browser creation form makes folder pools.

CLI scanning creates or reuses a named folder pool, activates it, and scans it:

```sh
.venv/bin/drum-atlas scan '/path/to/samples' --pool 'My drums'
.venv/bin/drum-atlas scan '/path/to/samples' --pool 'My drums' --baseline-only
```

An existing name must have the same roots. Use a new name for different roots.
Pool mutations from the web UI are serialized. Run CLI scans when no web scan is
running; click **Refresh index** in connected views after a CLI scan.

## Max for Live

No patch wiring changes are required. Sample `selected` messages, browser/Live
WebSocket selection and mode relay, Open Browser, adaptive dot sizing, and the
Live-safe wheel handling remain in place. The existing `scrub_sync` and `scrub`
messages still drive the Max-side 1/16 clock; Live transport must be running.
Backend auto-start from the device and distribution are deferred (see `TODO.md`).

## Browser

- **Click a point** to select and play. Click it again, press Space, or use Replay to retrigger.
- **Drag across points** to audition, with a configurable 90 / 150 / 250 ms minimum interval. A held point does not repeatedly fire. The hit radius is 24 pixels; empty space doesn't select an unrelated sound.
- Playback uses one voice with short fade transitions. Stale asynchronous loads cannot override a newer selection. A 64-sample decoded-audio cache makes revisits quicker.
- Scroll to zoom, Shift-drag to pan, Reset view to start again.
- Switch **CLAP / Timbral** to compare the same accepted sample set. Nearest-neighbor rankings always use full vectors, never map coordinates.
- Click neighbor rows to audition and select. **Audition all** plays that neighbor list in order, up to 2.2 seconds each. Click another sound or Stop to cancel.
- Search filenames or paths. **Include rejected / unembedded** exposes filtered files for listening and diagnosis. The keyboard-accessible sample list is an alternative to the canvas.
- Refresh index reloads the saved database after a scan. It does not initiate a scan.

## Scan and cache

WAV, AIFF, FLAC, OGG, and MP3 are enumerated recursively (decoder support depends on libsndfile). Directory symlinks are not followed and file symlinks are skipped. Duplicate paths from overlapping roots are deduplicated; distinct copies remain distinct.

SQLite uses WAL and per-file commits, so a stopped scan can resume. Absolute path, nanosecond mtime, size, analysis version, metadata, scores, diagnostics, and raw vectors are retained. Changed files invalidate both feature types. Decoder errors are recorded and retried next scan. Removed files are marked inactive only inside roots actually rescanned; unavailable roots fail before pruning. There is no content hashing, so byte changes that deliberately preserve both timestamp and size are not detected.

Only the first 12 seconds are decoded for analysis and previews, keeping memory bounded; file metadata keeps the full duration. Files longer than that are rejected by the one-shot screen. Leading/trailing near-silence is trimmed for analysis. The strongest channel is used for analysis to avoid phase cancellation; preview preserves up to two channels.

Re-run scanning to change thresholds:

```sh
drum-atlas scan '/path/to/samples' --one-shot 0.35 --drum 0.35
```

Unchanged analyses and eligible embeddings are reused. Lowering one-shotness can require new CLAP inference; changing percussion acceptance reuses existing CLAP vectors. Both UMAP layouts are cached by sample fingerprints, analysis versions, and thresholds. Baseline-only mode deliberately rebuilds the baseline-only cohort and removes any previous CLAP map. Re-run normally to restore a matched comparison.

Use one scanner at a time per database. Refresh the browser after it finishes; maps represent the most recently completed scan. This prototype uses exact linear nearest-neighbor search and a canvas; very large libraries need background jobs and more scalable search/rendering.

## What the representations mean

1. **One-shotness:** independent envelope heuristic based on active duration, distinct energy bursts, attack position, and decay. It rejects obvious loops and sustained sounds before neural inference. Rolls, flams, soft attacks, long cymbals, and some effects can be misclassified.
2. **Percussion likelihood:** for one-shot candidates, normalized CLAP audio features are compared with six percussion and six non-percussion text prompts. The best positive-minus-negative cosine margin is transformed with a fixed sigmoid (temperature 0.07). This is an interpretable ranking score, **not a calibrated probability**. Candidate CLAP embeddings are retained even when the percussion threshold rejects them, to allow cheap threshold adjustment. Baseline-only mode uses a weak attack/decay/noisiness heuristic and labels it as such.
3. **CLAP similarity:** normalized 512-dimensional audio embeddings, cosine distance. Audio is resampled to 48 kHz, trimmed, peak-normalized, and uses the processor's repeatpad policy for short hits. No filename or folder labels enter inference.
4. **Timbral similarity:** 32 dimensions: MFCC means/stds (excluding coefficient zero), log spectral centroid/bandwidth/rolloff, flatness, zero-crossing rate, log duration, attack time, and tail ratio. Standardization is fitted on the accepted cohort and saved; similarity uses Euclidean distance across all 32 dimensions.
5. **Visualization:** seeded UMAP for four or more samples, with metric matching the representation. One to three samples use an explicitly labeled small-set row layout. The 2-D view can distort distances; use the neighbor list for actual similarity.

CLAP implementation follows the [official Transformers CLAP documentation](https://huggingface.co/docs/transformers/model_doc/clap) and [LAION model card](https://huggingface.co/laion/clap-htsat-unfused). Projection follows [UMAP's documented API](https://umap-learn.readthedocs.io/en/latest/api.html).

## Test

```sh
pytest -q
drum-atlas demo /tmp/drum-atlas-demo
drum-atlas --db data/demo.sqlite scan /tmp/drum-atlas-demo --baseline-only
drum-atlas --db data/demo.sqlite serve
```

The generated library includes kicks, snares, hats, a loop, a sustained tone, and silence. Tests verify screening, persistent cache reuse/invalidation, missing/corrupt files, local preview decoding, and nearest-neighbor independence from map coordinates. The comparison report records what was actually tested against PML.

## Zoom into a pool combination

Check the pools you want, then press **Embed selection**. This builds both CLAP
and Timbral 2D layouts using only mapped samples in that pool union. It reuses
their existing full-dimensional vectors: no audio analysis or CLAP inference is
repeated. Filename search is still a display filter, not an embedding input.

**Global embed** restores the original global layout while keeping the pool
checkboxes. The map label indicates SELECTION when a subset layout is active.
Both views synchronize, including the compact Live view. Changing the pool
combination or library invalidates an incompatible active layout and displays
the global map. Up to 20 layouts are cached persistently; unchanged combinations
can be recalled without recomputing. Global coordinates and nearest-neighbor
metrics are untouched. Very small selections use a simple row layout.

## Double-click shortcuts

The project folder contains:

- `Launch.command`: starts the server and prevents a second launcher instance.
- `Open Drum Atlas.webloc`: opens the full interface in your default browser.
  You can copy this shortcut to your Desktop or drag it to the Dock.
- `Cleanup.command`: stops only the server recorded by this project's launcher.
  It checks process identity before stopping it; no samples, pools, or caches are
  deleted. Ctrl-C in the launch terminal works too. Stopping is optional when
  you finish a session, but frees the server's resources.

After this UI update, reload the Max web page once. The compact Live view hides
pool management before rendering, fixes toolbar/map grid placement, and refreshes
its library automatically when the server connection is re-established.
