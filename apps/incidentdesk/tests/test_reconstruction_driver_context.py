"""Synthetic saved facts for MIG-04B; never Gemini output."""

import uuid

import psycopg
import pytest

from evidence_import_fixtures import FIXTURES
from incident_report.domain import Report, ReportView, Role
from incident_report.evidence_import import inspect_bundle
from incident_report.facts import DriverObservation, OverviewFacts, PartyFact, StructuredFact


@pytest.fixture
def driver_report() -> Report:
    from incident_report.rules.driver import classify_driver_observations
    from test_reconstruction_cross_check import saved_facts

    decision = inspect_bundle(FIXTURES / "mig02-multi-review")
    assert decision.envelope
    road = decision.envelope.sources[0].original_video_sha256
    facts = saved_facts(road, 6.0, 6.2).model_copy(
        update={
            "parties": [
                PartyFact(
                    description="Synthetic <script>driver</script>",
                    party_code="P1",
                    view_id="b" * 64,
                    timestamp_seconds=0.0,
                    confidence=1.0,
                )
            ],
            "driver_observations": [
                DriverObservation(
                    kind=kind,
                    subject="Synthetic <script>driver</script>",
                    start_seconds=start,
                    end_seconds=end,
                    confidence=1.0,
                    view_id="b" * 64,
                )
                for kind, start, end in [
                    ("phone_in_hand", 4.0, 8.0),
                    ("looking_at_phone", 1.0, 3.0),
                    ("phone_on_mount", 0.0, 9.0),
                    ("seatbelt_worn", 0.0, 9.0),
                ]
            ],
        }
    )
    return Report(
        run_id=uuid.uuid4(),
        input_hash="a" * 64,
        prompt_version="synthetic",
        provenance="Synthetic test fixture, not Gemini output",
        summary="Synthetic test fixture",
        views=(
            ReportView(
                filename="road.avi", label="Synthetic road", sha256=road, role=Role.EXTERIOR, acquisition_method=None
            ),
            ReportView(
                filename="interior.mp4",
                label="Synthetic interior",
                sha256="b" * 64,
                role=Role.INTERIOR,
                acquisition_method=None,
            ),
        ),
        facts=facts,
        driver_assessments=classify_driver_observations(facts),
    )


def test_driver_intervals_on_own_clock(database_url: str, driver_report: Report) -> None:
    from incident_report.reconstruction.config import ReconstructionSettings
    from incident_report.reconstruction.presentation import context
    from incident_report.reconstruction.store import Workspace
    from incident_report.web.templating import build_environment

    with psycopg.connect(database_url) as conn:
        values = context(
            Workspace(conn, ReconstructionSettings(True, FIXTURES)),
            driver_report,
            ReconstructionSettings(True, FIXTURES),
        )
        html = build_environment().get_template("report.html").render(report=driver_report, print_view=False, **values)
    assert "Video analysis driver observation" in html
    assert (
        "phone in hand" in html and "looking at phone" in html and "phone on mount" in html and "seatbelt worn" in html
    )
    assert "4.000–8.000 s" in html
    assert "Own view clock" in html
    assert "&lt;script&gt;driver&lt;/script&gt;" in html and "<script>driver</script>" not in html
    assert driver_report.driver_assessments[0].reason in html


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
