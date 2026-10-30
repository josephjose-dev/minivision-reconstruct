# MIG-03 work log

Part A L2 — Tell the collaborator: producer_case_id remains an optional binding in
our envelope, identifying each unchanged producer case inside a shared application
case. Her manifests, CLI flags, schemas and workflows require no edits. Contract
README already documents the field and its single-view fallback.

## Implementation and boundaries

Branch `mig-03-timeline` starts at accepted integration `e825edb`. The application
workspace is behind `INCIDENTDESK_RECONSTRUCTION=true` (off by default), with local
`INCIDENTDESK_EVIDENCE_EXPORTS_ROOT` pointing at export bundles. There is no model
call and no reconstruction input to rules or AI. Report data and the PDF endpoint
remain unchanged. Browser printing hides the proposal workspace.

A preserves sequence intervals and covering frames and emits structured diagnostic
codes. B attaches immutable imports by the report view's original video SHA-256;
new revisions append supersession edges. C merges current proposals with app cited
moments on each view's native clock. Reviewer confirmation is explicitly a
reconstruction review, never officer approval. Rejected proposals are struck through;
off-table corrections never reuse an old citation.

E stores explicit same-view track associations, defaults to unmapped and keeps stale
history. Re-confirmation writes a new row on the current import/ref. Producer class
is carried in importer 1.4.0; old snapshots without it remain readable as unknown.
F stores reviewer offsets, required uncertainty and reliability (`unknown`,
`reviewer_estimated`, `shared_clock_documented`). Unknown reliability never creates
cross-camera order. Views aligned to a common reference are grouped by overlapping
uncertainty intervals; citations retain native times. Unresolved producer-order
groups stay in their per-view timeline.

Migration 0022 has up/down files and four append-only histories. After a disposable
test application exposed reset incompatibility, the unmerged migration was corrected
to follow 0016: validate incident existence under a row lock in the application,
without a `runs` FK. This preserves the existing benchmark/test `TRUNCATE runs`
convention without cascading into audit history. No historical migration, guard,
donor-imported test or collaborator path was changed.

## Local operation

Windows application (existing app environment and local database configuration):

```powershell
$env:INCIDENTDESK_RECONSTRUCTION='true'
$env:INCIDENTDESK_EVIDENCE_EXPORTS_ROOT='D:/minivision-incidentdesk/exports'
# From apps/incidentdesk, use the existing app startup command on 127.0.0.1:8000.
.venv/Scripts/python -m incident_report.evidence_import attach --incident <run-uuid> --attached-by 'Reviewer' relative-bundle
```

WSL, from this checkout:

```sh
export INCIDENTDESK_RECONSTRUCTION=true
export INCIDENTDESK_CASES_ROOT=/mnt/d/minivision-incidentdesk/cases
export RECONSTRUCTION_PYTHON=/mnt/d/minivision-incidentdesk/.venv-linux/bin/python
export RECONSTRUCTION_FFMPEG=/mnt/d/minivision-incidentdesk/linux-tools/ffmpeg/bin/ffmpeg
sh integration/launch_reconstruction_tools.sh
```

The launcher supplies only the unchanged entry points, `--cases-root`, replay's
`--media-port 8766 --ffmpeg`, and Streamlit server/browser flags. Streamlit binds to
127.0.0.1 on 8511/8512/8513. Usage statistics are disabled. No browser path reaches
these processes. The UI shows exact dropdown selections with a copy button; no
deep-link parameter exists in the collaborator tools.

Caddy is a separate dev binary, absent from dependency/lock files. This machine has
no winget command, so the official release was downloaded outside the repository:

```powershell
gh release download v2.11.7 --repo caddyserver/caddy --pattern caddy_2.11.7_windows_amd64.zip --pattern caddy_2.11.7_checksums.txt --dir D:/minivision-incidentdesk/dev-tools/caddy
# Compare archive SHA512 with the matching entry in the published checksums file.
Expand-Archive D:/minivision-incidentdesk/dev-tools/caddy/caddy_2.11.7_windows_amd64.zip D:/minivision-incidentdesk/dev-tools/caddy
D:/minivision-incidentdesk/dev-tools/caddy/caddy.exe validate --config integration/proxy/Caddyfile --adapter caddyfile
D:/minivision-incidentdesk/dev-tools/caddy/caddy.exe run --config integration/proxy/Caddyfile --adapter caddyfile
```

Version: `v2.11.7 h1:yj0Y4fYZGPkSvibBJ1sTWE33xC0fxztVyXEW5iIdUT4=`.
Browser address: `http://127.0.0.1:8080`. Without Caddy, the app's fixed tool routes
return a visible 503 explanation; Caddy also reports offline backends visibly.
These are local development processes, not a deployment/authentication boundary.

## Part D remains blocked

All three routes passed HTTP 200, health 200 and WebSocket 101 plus ping/pong
through Caddy. These transport checks do not prove manual UI correctness.

Computer Use stopped before browser inspection because it could not determine
Chrome's current URL confidently enough to enforce policy. No screenshots or saved
track-edit smoke are claimed. UI actions stopped; no alternative desktop automation
was used to bypass the block.

The replay producer hardcodes absolute media URLs at
`http://127.0.0.1:<media-port>/<token>` in `reconstruction/media.py`. Its existing flags
cannot replace that URL. Caddy exposes `/reconstruct/media/`, but the unchanged
browser component still requests port 8766 directly. Thus replay is linked out and
the full single-address requirement is not achieved. Chromium is needed for replay
exports per README; it was not installed. No producer code or renderer was patched.

Alternative found: the standard Streamlit baseUrlPath flag successfully routes the
tool shells and WebSockets without changing their code. It does not rewrite the
producer's media URLs. Owner/collaborator resolution is needed for that remaining
seam; an in-app Python/WebSocket proxy was not introduced.

## Tell the collaborator

- Keep producing existing case IDs, manifests and revisions; `producer_case_id`
  belongs to our envelope binding and does not require a producer change.
- We launch the three existing scripts with their existing cases-root/media/ffmpeg
  flags and Streamlit's baseUrlPath/server flags. Cases remain chosen by dropdown.
- Imported review confirmation remains a proposal review. Track associations and
  clock estimates are reviewer-set display aids, absent from fault/AI inputs.
- The absolute replay media URL prevents complete single-address routing with
  existing flags. No change to her code has been made or implicitly requested.

Full gate logs, fixture counts, focused commands and independent review findings
are in the donor `.agent_bridge/results/MIG-03-TIMELINE-WORKSPACE.md`. Independent
Claude critical acceptance remains required; no acceptance, merge, push or tag.
