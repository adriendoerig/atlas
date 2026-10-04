# Library and pool architecture

`samples` owns each canonical absolute path, file metadata, analysis version,
32 timbral features, CLAP embedding/version, and analysis diagnostics. The
`points` and `spaces` tables store global projected coordinates, normalized
full-dimensional vectors, and projection signatures. No embedding is stored in
a pool table.

- `pools(id, name UNIQUE, kind, created_at)` accepts `folder` and `manual` kinds.
- `pool_samples(pool_id, sample_id)` has a composite primary key and cascading
  foreign keys. Deleting a pool never deletes a sample.
- `pool_roots(pool_id, path)` records canonical source directories.
- `settings` stores the one-time pool migration marker and active pool IDs.

Migration is additive and idempotent. Existing sample IDs, blobs, and coordinates
are retained. A legacy nonempty database becomes the initially active Polaroit
pool; a sufficiently specific existing common parent becomes its folder root.
Otherwise it is a manual pool. A newly empty database starts with no pools.

Scanning enumerates roots before pruning, deduplicates canonical paths, then
reuses analysis only if mtime_ns, size, analysis version, and error state permit
it. CLAP has its own version check. Changed analysis invalidates CLAP. Scanning
an overlapping pool can therefore reuse both stages without running inference.
Individual analyses commit incrementally, so failed scans are retryable. Pool
membership is replaced atomically after a completed scan and projection update.
Missing roots fail before changing membership. Missing samples under successfully
scanned roots become globally inactive; manual references remain stored, but
inactive files are excluded from the active view. Empty available folders clear
their own pool membership. Corrupt discovered files remain recorded with errors.

Full-library projection signatures do not depend on active pool IDs. Selection
only filters the rendered points and neighbor candidates. Global map bounds are
kept when hiding pools. Neighbors are ranked with the original full vectors,
not 2-D coordinates.

## HTTP API

The backend binds to localhost only. JSON requests use Content-Type:
application/json. Interactive endpoint documentation is at `/docs`.

| Method | Path | Body / result |
| --- | --- | --- |
| GET | `/api/library` | Global samples, global spaces, current pool state |
| GET | `/api/pools` | Pools with roots/counts, active_pool_ids, distinct active sample_ids |
| POST | `/api/pools` | `{ "name":"Drums", "kind":"folder", "roots":["/path/to/drums"] }`; scans then activates |
| POST | `/api/pools` | `{ "name":"Favorites", "kind":"manual" }`; creates empty manual pool |
| PUT | `/api/pools/active` | `{ "ids":[1,2] }`; validates and persists selection |
| POST | `/api/pools/{id}/rescan` | Rescans remembered roots; returns analysis/cache statistics |
| DELETE | `/api/pools/{id}` | Removes pool and its references only |
| PUT | `/api/pools/{id}/members` | `{ "ids":[12,34] }`; atomically replaces manual pool sample IDs |

Pool results have `pools`, `active_pool_ids`, and `sample_ids`. Create additionally
returns `id`; rescan additionally returns `stats`. Rescans inherit the existing
global projection's thresholds and percussion method. A normal new database uses
CLAP. Baseline-only CLI scans deliberately switch the global projection method.

WebSocket `/api/sync?role=browser` or `role=live` retains the existing select,
mode, play, scrub_sync, scrub, and presence protocol. Initial state now contains
`pool_state`. Pool changes broadcast `type: "pools"`, `pool_state`, and
`library_changed`; clients reload global samples only after library changes.
A removed selection clears the shared selection and stops the scrub gesture.

Long scans run off the asynchronous event loop, allowing existing audition and
WebSocket traffic to continue. Web mutations are serialized. There is no durable
job queue or cross-process scanner lock: run one scanner per database.
