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


def test_duplicate_video_binding_is_rejected(tmp_path: Path) -> None:
    import json
    from copy import deepcopy
    from evidence_import_fixtures import synthetic_bundle
    root=synthetic_bundle(tmp_path)
    envelope=json.loads((root/'bundle.json').read_bytes())
    second=deepcopy(envelope['sources'][0]);second['view_id']='other-view'
    envelope['sources'].append(second)
    (root/'bundle.json').write_text(json.dumps(envelope))
    assert inspect_bundle(root).provenance_state=='rejected'
