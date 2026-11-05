"""Synthetic saved facts for MIG-04B; never Gemini output."""

from evidence_import_fixtures import FIXTURES
from incident_report.evidence_import import inspect_bundle
from incident_report.facts import OverviewFacts, PartyFact, StructuredFact


def test_unmapped_motion_names_missing_mapping() -> None:
    from incident_report.reconstruction.cross_check import compare_view

    decision = inspect_bundle(FIXTURES / "mig02-multi-review")
    assert decision.envelope
    source = decision.envelope.sources[0]
    facts = OverviewFacts(
        parties=[
            PartyFact(
                description="Synthetic white Toyota sedan",
                party_code="P1",
                view_id=source.original_video_sha256,
                timestamp_seconds=0.0,
                confidence=1.0,
            )
        ],
        events=[],
        candidate_collisions=[],
        behaviour_observations=[],
        location_conditions=[],
        structured_facts=[
            StructuredFact(
                subject="Synthetic white Toyota sedan",
                field="motion_state_before_contact",
                value="moving",
                other_party="",
                view_id=source.original_video_sha256,
                timestamp_seconds=7.0,
                confidence=1.0,
            )
        ],
    )
    row = next(
        r for r in compare_view(decision, source.view_id, source.original_video_sha256, facts, {}) if r.item == "Motion"
    )
    assert row.state == "cannot_compare"
    assert row.reason == "track is not mapped to Synthetic white Toyota sedan"
    mapped = next(
        r
        for r in compare_view(decision, source.view_id, source.original_video_sha256, facts, {"other-track": "P1"})
        if r.item == "Motion"
    )
    assert mapped.state == "cannot_compare"
    assert mapped.reason == "reconstruction has no observation of Synthetic white Toyota sedan at this time"
