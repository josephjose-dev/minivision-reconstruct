# Starting IncidentDesk

Two components use separate locked environments and exchange files only.

## Report app — Windows PowerShell

Create a dedicated PostgreSQL database `incidentdesk_dev` and a separate `incidentdesk_test_admin` database with a role allowed to create throwaway test databases. Use local credentials through libpq; never embed passwords in URLs. Set `DATABASE_URL` to the dedicated development database. Set `TEST_DATABASE_URL` separately for tests (see app `.env.test.example` comments). Never use the donor database.

```powershell
cd D:/minivision-incidentdesk/minivision-reconstruct/apps/incidentdesk
$env:DATABASE_URL = 'postgresql://postgres@127.0.0.1:5433/incidentdesk_dev'
uv sync --locked
uv run python -m incident_report.db migrate
uv run uvicorn --factory incident_report.web:create_app --port 8000
# Gate (Git Bash): bash scripts/check_all.sh
# PowerShell gate: ./scripts/check_all.ps1 -Base main
```

Replay samples at http://127.0.0.1:8000/samples require no model API key. Authenticate using the app's existing local admin/session flow. Do not enable live model processing for migration checks.

## Reconstruction worker — WSL Ubuntu

The existing user-space tools live outside the repository. No worker source changes are required. If a tool or locked wheel is missing, provision it separately; do not resolve a new lock or download models as part of checks.

```bash
cd /mnt/d/minivision-incidentdesk/minivision-reconstruct
export PATH=/mnt/d/minivision-incidentdesk/linux-tools/uv:/mnt/d/minivision-incidentdesk/linux-tools/ffmpeg/bin:$PATH
export UV_PROJECT_ENVIRONMENT=/mnt/d/minivision-incidentdesk/.venv-linux
export UV_CACHE_DIR=/mnt/d/minivision-incidentdesk/.uv-cache-linux
export PYTHONPATH=src
uv sync --locked --extra dev
uv run --locked python scripts/process_case.py --input <mp4> --case-id <id> --cases-root /mnt/d/minivision-incidentdesk/cases --ffprobe ffprobe
uv run --locked streamlit run scripts/review_tracks.py -- --cases-root /mnt/d/minivision-incidentdesk/cases
uv run --locked streamlit run scripts/calibrate_case.py -- --cases-root /mnt/d/minivision-incidentdesk/cases
uv run --locked streamlit run scripts/reconstruct_case.py -- --cases-root /mnt/d/minivision-incidentdesk/cases
# Remaining pipeline/export commands and flags: fork README.md.
uv run --locked pytest -q -rfE -p no:cacheprovider
```

## Shared cases

Windows `D:/minivision-incidentdesk/cases` maps to WSL `/mnt/d/minivision-incidentdesk/cases`. Reports must never store either absolute path. Relative evidence identifiers and the importer boundary are MIG-02 work, not implemented here.

## Review gate

The scoped protected-path guard intentionally rejects protected imports against `main` until owner review; no automatic blanket approval is applied. The offline dependency mode checks the exact frozen donor lock and declared imports; any lock change fails closed and needs a separate reviewed dependency ticket. It makes no package-index requests.
