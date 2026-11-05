"""MIG-04 synthetic saved facts; these are test fixtures, never Gemini output."""

from evidence_import_fixtures import FIXTURES
from incident_report.evidence_import import inspect_bundle
from incident_report.evidence_import.payloads import EventFields
from incident_report.facts import IncidentAssessment, OverviewFacts


def saved_facts(view: str, start: float, end: float) -> OverviewFacts:
    return OverviewFacts(
        parties=[],
        events=[],
        candidate_collisions=[],
        behaviour_observations=[],
        location_conditions=[],
        incident_assessments=[
            IncidentAssessment(
                view_id=view,
                assessment_note="Synthetic test fixture, not Gemini output",
                camera_role="fixed_camera",
                contact_state="contact_observed",
                contact_interval_start_seconds=start,
                contact_interval_end_seconds=end,
            )
        ],
    )


def test_contact_interval_contains_producer_peak() -> None:
    from incident_report.reconstruction.cross_check import compare_view

    decision = inspect_bundle(FIXTURES / "mig02-multi-review")
    assert decision.envelope
    source = decision.envelope.sources[0]
    event = next(
        r for r in decision.records if isinstance(r.data, EventFields) and r.data.event_type == "collision_candidate"
    )
    assert event.source_time is not None
    facts = saved_facts(source.original_video_sha256, event.source_time, event.source_time)
    rows = compare_view(decision, source.view_id, source.original_video_sha256, facts, {})
    assert rows[0].state == "cannot_compare"  # mapping is mandatory, never inferred
    assert rows[0].producer_frame == event.source_frame
