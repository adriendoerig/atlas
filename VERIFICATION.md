# Verification — 4 October 2026

Phase A: all four original pipeline tests passed from the new project-local
virtualenv before the pool refactor. Original source/database were preserved,
with a separate source/database snapshot and a Git checkpoint.

Phase B: all ten tests passed, including an installed-package run from
`/private/tmp` without relying on the source working directory. Tests cover:

- Legacy database migration, original blobs and IDs, and repeated opening.
- Distinct union, empty selection, persisted selection, deletion retaining samples.
- Manual membership replacement and rollback for invalid IDs.
- Overlapping-root timbral/CLAP cache reuse, changed/new/missing samples,
  outdated versions, and unavailable-root handling.
- Failed model initialization retaining prior pool membership for retry.
- CLI scan creating/reusing one folder pool.
- Pool state, selected sample, mode, scrub_sync and scrub WebSocket relay.
- Existing screening, corruption handling, audio preview and full-vector neighbors.

A snapshot of the user's actual two-pool database was rescanned:

| Pool | Found | Cached | New analysis | New CLAP embeddings | Errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Polaroit | 383 | 383 | 0 | 0 | 0 |
| Artist kicks | 449 | 449 | 0 | 0 | 0 |

Every saved global coordinate and vector remained identical after these cached
rescans. Both pools were then copied, using SQLite backup, to the permanent
Application Support database. Integrity checks passed. The global library has
832 records and 588 mapped samples at the current thresholds.

Browser checks against the final installed server on port 8765:

- Both pool counts and the 832-sample union appeared correctly.
- Individual and empty pool selections propagated to a separate `?view=live` tab.
- Restoring both pools restored the displayed points.
- Timbral mode and selected sample relayed to the compact view.
- The compact view rendered at 640 × 240 without the pool-management controls.
- CLAP mode and both checked pools were restored after checks.

The existing `drum_atlas_prototype` device was observed loaded in Live 12.
No Max patch was edited. The actual jweb~ host should be reloaded to pick up the
new JavaScript. Browser/compact-view behavior and the synchronization protocol
were verified; a fresh end-to-end listening test of the Max 1/16 metro was not
performed. Existing wheel handling, adaptive dot sizing, Open Browser, and Max
outlet messages were retained.

One existing Starlette/httpx deprecation warning remains in the test runner;
there are no failed tests.

Selection-map update: all 11 tests passed at the end of implementation. The new
coverage checks distinct-union layouts, original-vector inputs, cache reuse,
small selections, empty selections, invalidation, and unchanged global points.
The final server successfully built the real Polaroit subset with UMAP; a compact
Live-view tab showed SELECTION and synchronized back to global on button press.
Both original pool checkboxes and global mode were restored after verification.

Timing/pool/portability update: preserved the user's committed performance changes
in 5f06094. All 15 tests pass, including the new timing relay/reconnect/one-shot
gate and select-all union tests. The old neighbor test was updated to explicitly
request the user's opt-in neighbor path and to use an active pool; ordinary
requests are still asserted to return no neighbors. JavaScript and setup-shell
syntax checks pass. The package builds and installs locally.

Browser checks: 1-shot, 16ths, 8ths, and 4ths rendered; 8ths propagated from browser
to the compact view and 4ths/16ths propagated back. The live dropdown rendered at
640 x 240, with a scrollable nine-pool checklist. All pools selected 22,292 samples
in both views. The prior three-pool selection (605 samples) and one-shot timing
were restored after testing. The live clock itself still requires the documented
scrubdivision Max wiring and has not been listening-tested for 8ths/4ths.

Setup.command creates a fresh Python 3.12 environment and installs the project.
A code-only Mac ZIP excludes audio, user database, venv, and model weights. Archive
contents and executable flags are verified. Installation on another physical Mac
has not been tested; tested target remains Apple Silicon macOS/Python 3.12.
