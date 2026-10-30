"""Round 2 compatibility with unchanged producer exports."""
from pathlib import Path
import pytest
from evidence_import_fixtures import FIXTURES
from incident_report.evidence_import import inspect_bundle

@pytest.mark.parametrize('name',[p.name for p in FIXTURES.glob('mig02-*')])
def test_original_frame_times_resolve_without_rewriting(name: str) -> None:
    result=inspect_bundle(FIXTURES/name)
    assert 'source frame/time unresolved' not in result.issues
    for record in result.records:
        if record.kind=='track_reference':
            assert record.source_time is not None

@pytest.mark.parametrize('name',[p.name for p in FIXTURES.glob('mig02-*')])
def test_real_export_is_verified(name: str) -> None:
    result=inspect_bundle(FIXTURES/name)
    assert result.provenance_state=='verified',result.issues
    assert result.not_supplied_derived
