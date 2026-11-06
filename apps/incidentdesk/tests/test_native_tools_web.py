"""Native tools use attached selections, report access, escaped HTML and CSRF."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from access_client import authorized_client
from evidence_import_fixtures import FIXTURES
from incident_report.ai import ReplayAIConnection
from incident_report.domain import Origin, Report, ReportView, Role, Run, RunStatus
from incident_report.reconstruction.config import ReconstructionSettings
from incident_report.reconstruction.store import Workspace
from incident_report.runlog import RunLog
from incident_report.web import create_app


@pytest.mark.parametrize("response_kind", ["hostile", "captured"])
def test_track_page_uses_attached_selection_and_protects_write(
    run_log: RunLog, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, response_kind: str
) -> None:
    envelope = json.loads((FIXTURES / "mig02-relative/bundle.json").read_bytes())
    sha = envelope["sources"][0]["original_video_sha256"]
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
    import psycopg

    settings = ReconstructionSettings(True, FIXTURES)
    with psycopg.connect(run_log.database_url) as connection:
        workspace = Workspace(connection, settings)
        workspace.attach(report.run_id, "mig02-relative", "Reviewer")
        link = workspace.current(report.run_id)[0]
    monkeypatch.setenv("INCIDENTDESK_RECONSTRUCTION", "true")
    monkeypatch.setenv("INCIDENTDESK_EVIDENCE_EXPORTS_ROOT", str(FIXTURES))
    monkeypatch.setenv("INCIDENTDESK_NATIVE_TOOLS", "true")
    from incident_report.reconstruction.native_client import ToolsWorker

    calls: list[tuple[str, object]] = []

    def exchange(
        self: object, path: str, body: object = None, byte_range: str | None = None
    ) -> tuple[bytes, str, int, dict[str, str]]:
        calls.append((path, body))
        if "/calibration/" in path:
            if isinstance(body, dict) and body.get("action") == "save":
                return b'{"revision":"revision-003"}', "application/json", 200, {}
            return (
                (Path(__file__).parent / "fixtures/native_tracks/calibration-response.json").read_bytes(),
                "application/json",
                200,
                {},
            )
        if response_kind == "captured":
            return (
                (Path(__file__).parent / "fixtures/native_tracks/response.json").read_bytes(),
                "application/json",
                200,
                {},
            )
        return (
            json.dumps({"records": [], "track_ids": [1], "last_frame": 5, "case_id": "<script>evil</script>"}).encode(),
            "application/json",
            200,
            {},
        )

    monkeypatch.setattr(ToolsWorker, "exchange", exchange)
    app = create_app(ai=ReplayAIConnection(), run_log=run_log)
    client = authorized_client(app, run_log.database_url)
    url = f"/reports/{report.run_id}/tools/{link.link_id}/tracks"
    selected_frame = 68 if response_kind == "captured" else 0
    page = client.get(url, params={"frame": selected_frame})
    assert page.status_code == 200
    assert "Track review" in page.text
    assert "<script>evil</script>" not in page.text
    if response_kind == "hostile":
        assert "&lt;script&gt;evil&lt;/script&gt;" in page.text
    else:
        assert "mig02-relative" in page.text
        assert "observed" in page.text
        assert "automatic" in page.text
    assert calls[-1][0] == f"/cases/mig02-relative/tracks/staged-tracks?frame={selected_frame}"
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token is not None
    fields = {
        "csrf_token": token[1],
        "reviewer": "Reviewer",
        "reason": "Correct class",
        "action": "correct",
        "track_id": "1",
        "frame_number": "0",
        "class_name": "truck",
        "case_id": "../../outside",
    }
    count = len(calls)
    assert client.post(url, data={**fields, "csrf_token": "bad"}).status_code == 403
    assert client.post(url, data=fields, headers={"origin": "https://outside.example"}).status_code == 403
    assert len(calls) == count
    assert client.post(url, data=fields, follow_redirects=False).status_code == 303
    assert calls[-1][0] == "/cases/mig02-relative/tracks/staged-tracks"
    assert calls[-1][1] == {
        "reviewer": "Reviewer",
        "reason": "Correct class",
        "action": "correct",
        "payload": {"track_id": 1, "frame_number": 0, "class_name": "truck"},
    }
    entries = [
        entry
        for entry in run_log.audit.list_entries()
        if entry.action.startswith("native.tracks.") and entry.run_id == report.run_id
    ]
    assert [entry.action for entry in entries] == ["native.tracks.requested", "native.tracks.saved"]
    assert entries[-1].session_id is not None and entries[-1].run_id == report.run_id
    assert entries[-1].details == {
        "operation": "correct",
        "reviewer_sha256": hashlib.sha256(b"Reviewer").hexdigest(),
        "reason_sha256": hashlib.sha256(b"Correct class").hexdigest(),
    }
    box_fields = {**fields, "class_name": "", "bbox": "10,10,20,20"}
    assert client.post(url, data=box_fields, follow_redirects=False).status_code == 303
    assert calls[-1][1]["payload"] == {"track_id": 1, "frame_number": 0, "bbox": [10.0, 10.0, 20.0, 20.0]}
    create_fields = {**box_fields, "action": "create_track", "new_track_id": "8", "class_name": "car"}
    assert client.post(url, data=create_fields, follow_redirects=False).status_code == 303
    assert calls[-1][1]["payload"]["track_id"] == 8
    original_append = run_log.audit.append

    def fail_saved_audit(**kwargs: Any) -> object:
        if kwargs.get("action") == "native.tracks.saved":
            raise psycopg.OperationalError("Synthetic audit outage")
        return original_append(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(run_log.audit, "append", fail_saved_audit)
        count = len(calls)
        failed_confirmation = client.post(url, data=fields)
        assert failed_confirmation.status_code == 503
        assert "action completed" in failed_confirmation.text
        assert "do not repeat" in failed_confirmation.text
        assert len(calls) == count + 1
    assert client.get(url.replace(str(link.link_id), str(uuid.uuid4()))).status_code == 404
    calibration_url = url.removesuffix("tracks") + "calibration"
    calibration_page = client.get(calibration_url, params={"frame": 68})
    assert calibration_page.status_code == 200
    assert "Control points" in calibration_page.text
    assert "calibration-points.js" in calibration_page.text
    assert (
        calls[-1][0] == f"/cases/mig02-relative/calibration/{envelope['sources'][0]['calibration_revision']}?frame=68"
    )
    calibration_fields = {
        "csrf_token": token[1],
        "reviewer": "Reviewer",
        "reason": "Check points",
        "action": "preview",
        "frame": "68",
        "mode": "non_metric",
        "world_unit": "relative_units",
        "validation_tolerance": "0.01",
        "control_text": "0,0,0,0",
        "validation_text": "1,1,1,1",
        "features": "[]",
    }
    count = len(calls)
    assert client.post(calibration_url, data={**calibration_fields, "csrf_token": "bad"}).status_code == 403
    assert len(calls) == count
    assert client.post(calibration_url, data=calibration_fields).status_code == 200
    assert calls[-1][1]["features"] == []
    saved = client.post(calibration_url, data={**calibration_fields, "action": "save"}, follow_redirects=False)
    assert saved.status_code == 303
    assert "revision=revision-003" in saved.headers["location"] and "frame=68" in saved.headers["location"]
    assert client.get(saved.headers["location"]).status_code == 200
    assert calls[-1][0] == "/cases/mig02-relative/calibration/revision-003?frame=68"
    monkeypatch.setenv("INCIDENTDESK_NATIVE_TOOLS", "false")
    assert client.get(url).status_code == 404
