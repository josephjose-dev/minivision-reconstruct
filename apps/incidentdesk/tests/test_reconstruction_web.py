"""Workspace HTTP integration uses genuine share sessions and CSRF, with replay AI only."""

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from access_client import authorized_client
from evidence_import_fixtures import FIXTURES
from incident_report.ai import ReplayAIConnection
from incident_report.domain import Origin, Report, ReportView, Role, Run, RunStatus
from incident_report.reconstruction.config import ReconstructionSettings
from incident_report.reconstruction.store import Workspace
from incident_report.runlog import RunLog
from incident_report.storage.local import LocalEvidenceStore
from incident_report.web import create_app


def test_local_attach_mapping_alignment_and_flag_off_pages(
    run_log: RunLog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = json.loads((FIXTURES / "mig02-relative/bundle.json").read_bytes())["sources"][0]["original_video_sha256"]
    report = Report(
        run_id=uuid.uuid4(),
        input_hash="a" * 64,
        prompt_version="synthetic",
        provenance="synthetic",
        summary="Synthetic",
        views=(
            ReportView(filename="front.mp4", role=Role.EXTERIOR, label="Front", acquisition_method=None, sha256=sha),
        ),
    )
    run_log.record(
        Run(
            run_id=report.run_id,
            origin=Origin.REPLAY,
            created_at=datetime.now(UTC),
            input_hash=report.input_hash,
            report=report,
            status=RunStatus.SUCCEEDED,
            total_latency_ms=0,
        )
    )
    app = create_app(ai=ReplayAIConnection(), run_log=run_log, evidence=LocalEvidenceStore(tmp_path / "evidence"))
    client = authorized_client(app, run_log.database_url)
    url = f"/reports/{report.run_id}"
    monkeypatch.setenv("INCIDENTDESK_RECONSTRUCTION", "false")
    before = {suffix: client.get(url + suffix).content for suffix in ("", "/review", "/print")}
    monkeypatch.setenv("INCIDENTDESK_RECONSTRUCTION", "true")
    monkeypatch.setenv("INCIDENTDESK_EVIDENCE_EXPORTS_ROOT", str(FIXTURES))
    page = client.get(url + "/review")
    assert page.status_code == 200
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token is not None
    fields = {"csrf_token": token[1], "bundle": "mig02-relative", "reviewer": "synthetic reviewer"}
    assert client.post(url + "/reconstruction/attach", data={"bundle": "mig02-relative"}).status_code == 403
    assert (
        client.post(
            url + "/reconstruction/attach", data=fields, headers={"origin": "https://outside.example"}
        ).status_code
        == 403
    )
    headers = {"origin": "https://testserver"}
    assert (
        client.post(url + "/reconstruction/attach", data=fields, headers=headers, follow_redirects=False).status_code
        == 303
    )
    html = client.get(url + "/review").text
    assert "Reconstruction proposal" in html and "Choose in the tool dropdown" in html
    assert "Reconstruction proposal" not in client.get(url + "/print").text
    with psycopg.connect(run_log.database_url) as conn:
        workspace = Workspace(conn, ReconstructionSettings(True, FIXTURES))
        link = workspace.current(report.run_id)[0]
        ref = next(r.track_refs[0] for r in workspace.decision(link.import_id).records if r.kind == "track_reference")
    mapping = {
        "csrf_token": token[1],
        "import_id": link.import_id,
        "view": sha,
        "track_ref": ref,
        "mapping_action": "cannot_determine",
        "reviewer": "synthetic",
        "reason": "occluded",
    }
    assert (
        client.post(url + "/reconstruction/mapping", data=mapping, headers=headers, follow_redirects=False).status_code
        == 303
    )
    alignment = {
        "csrf_token": token[1],
        "view": sha,
        "reference": sha,
        "offset": "0",
        "clock_reliability": "reviewer_estimated",
        "reviewer": "synthetic",
        "reason": "reference",
    }
    assert (
        client.post(
            url + "/reconstruction/alignment", data=alignment, headers=headers, follow_redirects=False
        ).status_code
        == 422
    )
    alignment["uncertainty"] = "0.1"
    assert (
        client.post(
            url + "/reconstruction/alignment", data=alignment, headers=headers, follow_redirects=False
        ).status_code
        == 303
    )
    assert "occluded" not in run_log.get(report.run_id).report.model_dump_json()  # type: ignore[union-attr]
    monkeypatch.setenv("INCIDENTDESK_RECONSTRUCTION", "false")
    assert before == {suffix: client.get(url + suffix).content for suffix in before}
    assert client.post(url + "/reconstruction/attach", data=fields, headers=headers).status_code == 404
    monkeypatch.setenv("INCIDENTDESK_RECONSTRUCTION", "true")
    client.cookies.clear()
    assert client.post(url + "/reconstruction/attach", data=fields, headers=headers).status_code == 403
