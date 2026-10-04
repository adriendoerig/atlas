# Drum Atlas — V0

A local Python sample browser for testing whether nearby samples sound meaningfully similar. No Max for Live layer yet.

## Run

Requires Python 3.10 or newer (tested with Python 3.12 on Apple Silicon).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
drum-atlas scan '/path/to/samples' '/another/sample/root'
drum-atlas serve
```

Open http://127.0.0.1:8765. The first scan downloads `laion/clap-htsat-unfused` into `data/models`; subsequent inference runs locally. The model revision is pinned in the source for repeatability. Audio is never uploaded. A baseline-only scan requires no model download:

```sh
drum-atlas scan '/path/to/samples' --baseline-only
```

Database option precedes the command:

```sh
drum-atlas --db data/pml-test.sqlite serve
```

The supplied PML test database references original files on this computer. It contains no audio. Run the launch script on this machine or set up a fresh environment elsewhere.

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
