"""MIG-03 carry-overs at the public import boundary."""

from pathlib import Path

import pytest

from evidence_import_fixtures import FIXTURES, synthetic_bundle
from incident_report.evidence_import import inspect_bundle
from incident_report.evidence_import.payloads import SequenceFields


@pytest.mark.parametrize("name", [p.name for p in FIXTURES.glob("mig02-*")])
def test_real_sequence_windows_are_source_intervals(name: str) -> None:
    result = inspect_bundle(FIXTURES / name)
    rows = [r for r in result.records if isinstance(r.data, SequenceFields)]
    assert rows
    assert all(not r.needs_review for r in rows)
    assert all(r.data.covering_frames is not None for r in rows)


def test_window_without_a_frame_is_quarantined(tmp_path: Path) -> None:
    from typing import Any

    def change(documents: dict[str, list[dict[str, Any]]], envelope: dict[str, Any]) -> None:
        for name, rows in documents.items():
            if name.endswith("/sequence.json"):
                rows[0]["entries"][0]["time_window"] = [0.001, 0.039]

    result = inspect_bundle(synthetic_bundle(tmp_path, transform=change))
    record = next(r for r in result.records if isinstance(r.data, SequenceFields) and r.data.rank == 1)
    assert isinstance(record.data, SequenceFields)
    assert record.data.time_window == (0.001, 0.039)
    assert record.data.covering_frames is None and record.needs_review
    assert any("window contains no source frame" in issue for issue in result.issues)
