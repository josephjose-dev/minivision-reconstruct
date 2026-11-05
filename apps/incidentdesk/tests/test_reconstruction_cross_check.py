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


import pytest


@pytest.mark.parametrize(
    "state,start,end,expected,delta",
    [
        ("contact_observed", 6.0, 6.2, "agree", None),
        ("contact_observed", 4.0, 5.0, "disagree_time", 1.08),
        ("no_contact_observed", None, None, "model_miss", None),
        ("contact_possible_obscured", 6.0, 6.2, "cannot_compare", None),
        ("cannot_assess", None, None, "cannot_compare", None),
    ],
)
def test_contact_time_states(
    state: str, start: float | None, end: float | None, expected: str, delta: float | None
) -> None:
    from incident_report.reconstruction.cross_check import compare_view

    d = inspect_bundle(FIXTURES / "mig02-multi-review")
    assert d.envelope
    s = d.envelope.sources[0]
    f = saved_facts(s.original_video_sha256, 6.0, 6.2)
    a = f.incident_assessments[0].model_copy(
        update={"contact_state": state, "contact_interval_start_seconds": start, "contact_interval_end_seconds": end}
    )
    f = f.model_copy(update={"incident_assessments": [a]})
    maps = {
        r: c
        for e in d.records
        if isinstance(e.data, EventFields) and e.data.event_type == "collision_candidate"
        for r, c in zip(e.track_refs, ("P1", "P2"), strict=True)
    }
    rows = compare_view(d, s.view_id, s.original_video_sha256, f, maps)
    row = next(r for r in rows if r.item == "Contact time" and r.producer_time == 6.08)
    assert row.state == expected
    if delta is not None:
        assert row.difference_seconds == pytest.approx(delta)
    assert row.video_times == (() if start is None else (start, end))
    assert any(r.state == "cannot_compare" and r.producer_time is None for r in rows)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mig02-001-05-near-miss-crossing", "tracker_miss"),
        ("mig02-001-06-normal-crossing", "reconstruction_unavailable"),
    ],
)
def test_no_candidate_is_distinct_from_missing_inputs(name: str, expected: str) -> None:
    from incident_report.reconstruction.cross_check import compare_view

    d = inspect_bundle(FIXTURES / name)
    assert d.envelope
    s = d.envelope.sources[0]
    rows = compare_view(d, s.view_id, s.original_video_sha256, saved_facts(s.original_video_sha256, 4.0, 5.0), {})
    assert rows[0].state == expected
