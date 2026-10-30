"""Local evidence boundary: hostile bundles are recorded, never executed."""

from pathlib import Path

from incident_report.evidence_import import inspect_bundle


def test_unknown_contract_is_a_recorded_rejection(tmp_path: Path) -> None:
    (tmp_path / "bundle.json").write_text('{"contract_version":"999"}', encoding="utf-8")
    decision = inspect_bundle(tmp_path)
    assert decision.provenance_state == "rejected"
    assert decision.issues
    assert decision.records == ()
