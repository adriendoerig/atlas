# PML prototype validation — 4 October 2026

## What ran

Scanned the **340 audio files** in the Polaroit Sample Pack inside `/Library/Audio/PML/PMLxStilVorTalentxPolaroit - Sample Pack`. This is a bounded real-library test, not the entire 44 GB PML collection (15,692 WAV files were enumerated across that collection).

- All 340 files decoded successfully.
- Envelope screening at **0.45** produced **173 candidates**.
- Actual CLAP inference ran locally for all 173, storing each 512-dimensional embedding.
- CLAP percussion acceptance at **0.50** kept **150 samples**.
- CLAP and timbral UMAP maps contain exactly the same 150 samples.
- A complete repeat scan reused all 340 analyses, computed **zero new embeddings**, and retained 150 mapped samples.
- Original samples remain in their original folders and were not changed or copied.

## Filtering observations

| Pack category | Files | Passed one-shot screen | Accepted after CLAP |
|---|---:|---:|---:|
| Kicks | 19 | 18 | 18 |
| Snares | 8 | 7 | 7 |
| Hats | 24 | 24 | 24 |
| Claps | 19 | 18 | 18 |
| Toms | 23 | 19 | 19 |
| Cymbals | 14 | 6 | 6 |
| Shakers | 13 | 13 | 13 |
| Percs | 9 | 7 | 7 |
| Field-recorded one-shots | 63 | 48 | 38 |
| Piano chords | 20 | 13 | 0 |
| Drum loops | 71 | 0 | 0 |
| Music loops | 21 | 0 | 0 |
| Piano harmony recordings | 21 | 0 | 0 |
| Ambience | 9 | 0 | 0 |
| Risers | 6 | 0 | 0 |

The separate stages are useful: piano chords often have one clear onset and decay, so 13 passed the envelope check. CLAP rejected all 13. Field-recorded impacts are intentionally ambiguous: they can be useful percussion even when they are not musical instruments.

The main weakness is **recall**, particularly cymbals (6/14 retained). Multiple energy peaks, slower attacks, and longer decays can lower one-shotness. These should be inspected in the rejected list before making the screen stricter or scanning the full collection. Folder labels are only a rough reference, not verified ground truth; no filenames or folder names were used by the classifier.

## CLAP versus timbral features

These are **qualitative observations from neighbor identities and measured features**, supported by a folder-label diagnostic. They are not a completed human listening study or evidence that one representation always sounds better.

- **Kicks:** both representations find coherent kick neighborhoods. For `Kick_001_5am`, all five nearest neighbors are kicks in both spaces, but their ordering differs. CLAP first returns `Kick_006_A24`; timbral first returns `Kick_002_A09`.
- **Toms:** CLAP more consistently stays within tom-like and kick-like groups. For `Tom_003_A09`, CLAP returns kicks and another tom; timbral returns field-recorded jumps and plastic-box impacts. Those cross-category matches could be musically useful, but need listening.
- **Hats:** the baseline is competitive overall. For `Hat_001_5am`, CLAP returns hats and shakers, while the baseline mixes a clap, shaker, snares, and a stone clap. This example favors CLAP semantically, although the aggregate folder diagnostic slightly favors the baseline.
- **Claps / impacts:** both cross the boundary between conventional drums and found percussion. `Clap_001_5am` retrieves bricks and plastic boxes in CLAP and plastic boxes, a brick, and stone claps in the baseline. That is a useful case to audition rather than judge by filenames alone.
- **Snares:** both spaces mix snares, claps, hats, and other transients. Neither cleanly separates this small seven-sample snare cohort.

Average fraction of the five nearest neighbors sharing the seed's source folder:

| Seed category | CLAP | Timbral |
|---|---:|---:|
| Kicks | 93.3% | 92.2% |
| Toms | 67.4% | 47.4% |
| Claps | 70.0% | 63.3% |
| Hats | 65.8% | 71.7% |
| Snares | 25.7% | 20.0% |
| Field-recorded one-shots | 92.6% | 84.7% |

This diagnostic rewards pack organization, not perceptual quality. It is particularly coarse for the heterogeneous Field Recordings category. Both methods were evaluated on the same CLAP-filtered cohort, so this is not an independent evaluation of filtering or a benchmark of generalization. Both should remain available for now.

## Browser and automated checks

Four automated tests pass, covering envelope screening; metadata and embedding reuse/invalidation; missing and corrupt files; invalid roots; matched comparison cohorts; full embedding dimensions; audio preview responses; and nearest-neighbor independence from 2-D coordinates. The CLAP cache unit test uses a stub model; the 173-file run above separately validates actual model inference.

In the running browser, point clicking started playback and populated scores, paths, waveforms, and neighbors. Dragging changed from `Kick_006_A24` to `Kick_003_A20`. Switching representations changed the neighbor rankings while retaining selection. Neighbor-sequence playback, Stop, and search were exercised. The browser reported no JavaScript warnings or errors. This verifies browser decoding/playback state, not the quality of the physical audio output or subjective similarity.

## Next listening pass

Use the browser to select a kick, tom, hat, snare, and found impact. Replay the seed, audition its neighbors, switch representations, and repeat. Judge attack, body, decay, brightness, pitch, and whether the neighboring sound would substitute usefully in a pattern. Inspect rejected cymbals and flams before lowering the one-shot threshold. Tune with those judgments before scaling up or building the Ableton layer.
