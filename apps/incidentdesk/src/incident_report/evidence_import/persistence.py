"""Persist an inspection using the app's existing local PostgreSQL connection.

The importer owns no connection setup, credentials, or outbound client. Callers supply
an already-open local DB connection. Serialization occurs before insertion; immutable
rows and per-import locks prevent partial or concurrent duplicate imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ImportDecision
from .reader import inspect_bundle


def load_import(import_id: str, connection: Any) -> ImportDecision | None:
    row = connection.execute("SELECT decision FROM evidence_imports WHERE import_id=%s", (import_id,)).fetchone()
    if row is None:
        return None
    raw = {
        name: bytes(content)
        for name, content in connection.execute(
            "SELECT artifact_path, content FROM evidence_import_artifacts WHERE import_id=%s", (import_id,)
        )
    }
    raw.update(
        {
            name: bytes(content)
            for name, content in connection.execute(
                "SELECT a.artifact_path,b.content FROM evidence_import_failed_artifacts a JOIN evidence_import_failed_blobs b USING (sha256) WHERE a.import_id=%s",
                (import_id,),
            )
        }
    )
    return ImportDecision.model_validate({**row[0], "raw_artifacts": raw})


def import_bundle(directory: Path, connection: Any) -> ImportDecision:
    """Inspect and atomically append; byte-identical content returns its existing decision."""
    decision = inspect_bundle(directory)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (int(decision.import_id[:15], 16),))
        existing = load_import(decision.import_id, connection)
        if existing is not None:
            return existing
        connection.execute(
            "INSERT INTO evidence_imports (import_id,importer_version,provenance_state,decision,raw_envelope) VALUES (%s,%s,%s,%s::jsonb,%s)",
            (
                decision.import_id,
                decision.importer_version,
                decision.provenance_state,
                decision.model_dump_json(),
                decision.raw_artifacts.get("bundle.json") if decision.read_complete else None,
            ),
        )
        for name, content in decision.raw_artifacts.items():
            if not decision.read_complete:
                connection.execute(
                    "INSERT INTO evidence_import_failed_blobs (sha256,content) VALUES (%s,%s) ON CONFLICT (sha256) DO NOTHING",
                    (decision.source_hashes[name], content),
                )
                connection.execute(
                    "INSERT INTO evidence_import_failed_artifacts (import_id,artifact_path,sha256) VALUES (%s,%s,%s)",
                    (decision.import_id, name, decision.source_hashes[name]),
                )
                continue
            connection.execute(
                "INSERT INTO evidence_import_artifacts (import_id,artifact_path,sha256,content) VALUES (%s,%s,%s,%s)",
                (decision.import_id, name, decision.source_hashes[name], content),
            )
        for record in decision.records:
            connection.execute(
                "INSERT INTO evidence_import_records (import_id,record_id,kind,view_id,record) VALUES (%s,%s,%s,%s,%s::jsonb)",
                (decision.import_id, record.record_id, record.kind, record.view_id, record.model_dump_json()),
            )
    return decision
