# Evidence contract 1.0

The report app accepts a **local directory** containing `bundle.json` and only its
listed artifacts. ZIP extraction is deliberately not offered. The JSON Schemas use
Draft 2020-12. The stdlib/Pydantic importer does not import the worker, AI package,
network clients, or execute bundle contents. Persistence accepts an already-open
local application PostgreSQL connection; it never creates a connection itself.

`bundle.json` is the import envelope. It pins producer git revision, case, creation
time, local-only policy, config/model identifiers, artifact SHA-256s and one source
binding per externally assigned view. Each binding pins reconstruction, movement,
incident and review runs, tracking/calibration revisions, original-video digest,
metadata, zero-based frame convention and transformation history. Video bytes stay
outside these JSON fixtures; a digest binding is not authentication or proof the
provided video is genuine. Upstream absolute source paths are preserved inertly;
resolution uses included relative artifact names and digests only.

Normalized records preserve the full original payload. They distinguish source
bindings/frame maps, namespaced track references, geometry, event proposals,
assessments, review overlays and sequence entries. Identity hashes encode separate
case/view/tracking-run/revision/track-ID components; track references are never
parties. Producer event IDs remain in `original.event_id`; source artifact path and
view identify them across runs. Geometry retains its original units, calibration
manifest link, uncertainty and nulls; no unit conversion occurs. Ordering ambiguity
and supporting/contrary evidence remain in original payloads.

The source timestamp table is authoritative. Citation fields are populated only
when the frame and timestamp match that table exactly; corrections without an exact
source timestamp have `needs_review=true` and null citation fields. Original windows,
phases, signals and peak frame remain original beside the effective correction.
Source time is never substituted with replay/export time. Floating-point differences
in producer files are conservatively flagged rather than silently rounded.

Review revisions are complete snapshots, hash-chained to earlier snapshots and the
incident manifest. The latest snapshot alone supplies decisions in force, including
an empty snapshot. Original and effective values remain separate. Reviewer strings
are unauthenticated. Parent event status is checked for each assessment. Every
record has `affirmative=false`, `officer_approved=false` and `rule_source=null`:
acceptance here means structural/provenance acceptance, never accepted fault facts.
MIG-03/MIG-04 must implement their own authenticated officer review boundary.

Unknown versions, unsafe bundle paths, malformed/oversized JSON and hash mismatches
reject the whole bundle. Missing upstream evidence quarantines all normalized
records as `incomplete_provenance`; available originals remain listed. Empty candidate
lists are explicit missing-input states, never a finding of no incident. Original
artifact bytes, raw envelope, hashes, decisions and normalized rows are stored in
append-only tables by migration 0020 (with a destructive down migration for disposable
data). Byte-identical imports return the existing decision; changed runs/reviews
produce distinct imports. Database owner/superuser privileges can still drop tables
or disable triggers; this is an application immutability guarantee, not protection
against the database administrator.

Resource budgets in `models.py` are **project assumptions, to be validated**, not
scientific thresholds: 16 MiB/file, 256 KiB/record, 64 MiB/bundle, 512 files, 1024
filesystem entries and 100,000 parsed records. Input must be on a fixed local drive
on Windows; UNC/device paths, symlinks, junctions, linked ancestors and special files
are refused. Supply a stable directory; this is not an OS sandbox against another
process concurrently replacing filesystem ancestors.

Versioning: contract `1.0`, importer `1.0.0`. Unknown contract or producer schema
versions reject rather than guessing compatibility. Regenerate schemas from the
Pydantic models when the reviewed contract changes. No existing app behavior or
fault engine is connected to this module.

Unsupported crop/rotation/scaling transformations reject explicitly; the currently
supported transformation descriptor is the producer reconstruction replay with its
relative frame-map path. Native source tables support variable frame rates without
inventing a frame/rate conversion. JSON text that PostgreSQL JSONB cannot represent
(NUL or invalid Unicode) rejects while its raw bytes stay in BYTEA. If reading is
refused before a complete content identity is available, the rejection has a unique
attempt ID; it cannot be deduplicated as an unrelated unreadable attempt. Such
unreadable attempts have no claimed byte-identity guarantee.
