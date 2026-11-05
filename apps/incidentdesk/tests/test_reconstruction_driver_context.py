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
    from incident_report.facts import DriverObservationKind

    intervals: list[tuple[DriverObservationKind, float, float]] = [
        ("phone_in_hand", 4.0, 8.0),
        ("looking_at_phone", 1.0, 3.0),
        ("phone_on_mount", 0.0, 9.0),
        ("seatbelt_worn", 0.0, 9.0),
    ]
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
                for kind, start, end in intervals
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


@pytest.mark.parametrize(
    "mode,expected_start,uncertainty", [("direct", 5.0, 0.5), ("reverse", 5.0, 0.5), ("shared", 5.0, 0.75)]
)
def test_driver_context_uses_only_explicit_clock_links(
    driver_report: Report, mode: str, expected_start: float, uncertainty: float
) -> None:
    from incident_report.reconstruction.alignment import Alignment
    from incident_report.reconstruction.driver_context import driver_panels

    interior, road = "b" * 64, driver_report.views[0].sha256
    alignments: tuple[Alignment, ...]
    if mode == "direct":
        alignments = (Alignment(interior, road, 1.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "test fixture"),)
    elif mode == "reverse":
        alignments = (Alignment(road, interior, -1.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "test fixture"),)
    else:
        alignments = (
            Alignment(interior, "c" * 64, 3.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "test fixture"),
            Alignment(road, "c" * 64, 2.0, 0.25, "reviewer_estimated", "Road reviewer", "test fixture"),
        )
    panel = driver_panels(driver_report, {}, alignments)[interior]
    context = panel.roads[0]
    assert context.alignment is not None
    phone = next(t for t in context.timings if t.observation.kind == "phone_in_hand")
    assert phone.start == expected_start and phone.end == 9.0
    assert context.alignment.uncertainty == uncertainty
    assert phone.contact.time == 6.0
    assert phone.start_difference == -1.0 and phone.end_difference == 3.0
    assert phone.relation == "overlaps contact time"
    assert "Synthetic reviewer" in context.alignment.reviewers


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (5.5, 6.5, "overlaps contact time"),
        (5.51, 6.5, "possible overlap (within ±0.5 s)"),
        (6.5, 7.0, "possible overlap (within ±0.5 s)"),
        (6.51, 7.0, ""),
        (5.9, 6.1, "possible overlap (within ±0.5 s)"),
    ],
)
def test_overlap_requires_all_offsets(driver_report: Report, start: float, end: float, expected: str) -> None:
    from incident_report.reconstruction.alignment import Alignment
    from incident_report.reconstruction.driver_context import driver_panels

    assert driver_report.facts
    observation = driver_report.facts.driver_observations[0].model_copy(
        update={"start_seconds": start, "end_seconds": end}
    )
    report = driver_report.model_copy(
        update={"facts": driver_report.facts.model_copy(update={"driver_observations": [observation]})}
    )
    alignment = Alignment(
        "b" * 64, report.views[0].sha256, 0.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "fixture"
    )
    timing = driver_panels(report, {}, (alignment,))["b" * 64].roads[0].timings[0]
    assert timing.relation == expected


@pytest.mark.parametrize("mode", ["absent", "unknown", "different_reference", "latest_unknown"])
def test_unaligned_driver_has_no_timing_relation(driver_report: Report, mode: str) -> None:
    from incident_report.reconstruction.alignment import Alignment
    from incident_report.reconstruction.driver_context import driver_panels

    a = Alignment(
        "b" * 64, driver_report.views[0].sha256, 1.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "fixture"
    )
    alignments: tuple[Alignment, ...] = () if mode == "absent" else (a,)
    if mode == "unknown":
        alignments = (Alignment(a.view, a.reference, a.offset, a.uncertainty, "unknown", a.reviewer, a.reason),)
    if mode == "latest_unknown":
        alignments += (Alignment(a.view, a.reference, a.offset, a.uncertainty, "unknown", a.reviewer, a.reason),)
    if mode == "different_reference":
        alignments = (Alignment(a.view, "c" * 64, 1.0, 0.5, a.clock_reliability, a.reviewer, a.reason),)
    road = driver_panels(driver_report, {}, alignments)["b" * 64].roads[0]
    assert road.alignment is None and road.timings == ()


def test_aligned_saved_import_contact_citations_and_offline_render(
    database_url: str, driver_report: Report, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    from incident_report.facts import CollisionObservation
    from incident_report.reconstruction.alignment import Alignment, record_alignment
    from incident_report.reconstruction.config import ReconstructionSettings
    from incident_report.reconstruction.presentation import context
    from incident_report.reconstruction.store import Workspace
    from incident_report.web.templating import build_environment

    assert driver_report.facts
    road = driver_report.views[0].sha256
    contact = CollisionObservation(
        kind="contact_other",
        subject="Synthetic <script>driver</script>",
        other_party="barrier",
        injury_grade="unknown",
        view_id=road,
        timestamp_seconds=6.1,
        confidence=1.0,
    )
    report = driver_report.model_copy(
        update={"facts": driver_report.facts.model_copy(update={"collision_observations": [contact]})}
    )
    settings = ReconstructionSettings(True, FIXTURES)
    saved = report.model_dump_json()
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO runs(run_id,origin,created_at,input_hash,report,status,total_latency_ms) VALUES (%s,'replay',now(),%s,%s::jsonb,'succeeded',0)",
            (report.run_id, report.input_hash, saved),
        )
        conn.commit()
        workspace = Workspace(conn, settings)
        workspace.attach(report.run_id, "mig02-multi-review", "Synthetic reviewer")
        record_alignment(
            workspace,
            report.run_id,
            Alignment("b" * 64, road, 1.0, 0.5, "reviewer_estimated", "Synthetic <script>reviewer</script>", "fixture"),
        )

        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("network attempted during driver timeline render")

        monkeypatch.setattr(socket, "create_connection", forbidden)
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        values = context(workspace, report, settings)
        timings = values["driver_context"]["b" * 64].roads[0].timings
        phone = [t for t in timings if t.observation.kind == "phone_in_hand"]
        assert {t.contact.time for t in phone} == {6.0, 6.2, 6.1, 6.08}
        peak = next(t for t in phone if t.contact.label == "Reconstruction candidate peak")
        assert peak.contact.source_frame == 152
        assert peak.contact.review_status == "Confirmed by reconstruction reviewer"
        html = build_environment().get_template("report.html").render(report=report, print_view=False, **values)
        assert "aligned 5.000–9.000 s" in html
        assert "±0.5 s" in html and "-1.000 s / +3.000 s" in html
        assert "&lt;script&gt;reviewer&lt;/script&gt;" in html
        assert "Video analysis contact interval start" in html and "Video analysis contact interval end" in html
        assert (
            "Video analysis contact timestamp" in html
            and "Reconstruction candidate peak: 6.080 s, source frame 152" in html
        )
        assert report.model_dump_json() == saved


@pytest.mark.parametrize("change", ["rejected", "unknown_corrected", "needs_review"])
def test_unusable_candidate_never_supplies_driver_timing(driver_report: Report, change: str) -> None:
    from dataclasses import replace

    from incident_report.reconstruction.alignment import Alignment
    from incident_report.reconstruction.driver_context import driver_panels
    from incident_report.reconstruction.presentation import ViewPanel
    from incident_report.reconstruction.timeline import timeline_groups

    decision = inspect_bundle(FIXTURES / "mig02-multi-review")
    assert decision.envelope
    road = driver_report.views[0].sha256
    groups = timeline_groups(decision, decision.envelope.sources[0].view_id, road, ())
    groups = tuple(
        replace(
            g,
            rows=tuple(
                replace(
                    r,
                    rejected=change == "rejected",
                    needs_review=change == "needs_review",
                    source_time=None if change == "unknown_corrected" else r.source_time,
                )
                for r in g.rows
            ),
        )
        for g in groups
    )
    panels = {road: ViewPanel(groups, (), ())}
    alignment = Alignment("b" * 64, road, 0.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "fixture")
    timings = driver_panels(driver_report, panels, (alignment,))["b" * 64].roads[0].timings
    assert timings
    if change == "needs_review":
        assert any(
            t.contact.label == "Reconstruction candidate peak" and "Needs review" in t.contact.review_status
            for t in timings
        )
    else:
        assert all(t.contact.label != "Reconstruction candidate peak" for t in timings)


@pytest.mark.parametrize("kind", ["obscured", "overturned", "needs_review", "unresolved"])
def test_contact_context_preserves_uncertain_candidates_with_caveats(driver_report: Report, kind: str) -> None:
    from dataclasses import replace

    from incident_report.facts import CollisionObservation
    from incident_report.reconstruction.alignment import Alignment
    from incident_report.reconstruction.driver_context import driver_panels
    from incident_report.reconstruction.presentation import ViewPanel
    from incident_report.reconstruction.timeline import timeline_groups

    assert driver_report.facts
    facts = driver_report.facts
    road = driver_report.views[0].sha256
    panels = {}
    if kind == "obscured":
        facts = facts.model_copy(
            update={
                "incident_assessments": [
                    facts.incident_assessments[0].model_copy(update={"contact_state": "contact_possible_obscured"})
                ]
            }
        )
    elif kind == "overturned":
        facts = facts.model_copy(
            update={
                "incident_assessments": [],
                "collision_observations": [
                    CollisionObservation(
                        kind="vehicle_overturned",
                        subject="Synthetic <script>driver</script>",
                        other_party="",
                        injury_grade="unknown",
                        view_id=road,
                        timestamp_seconds=6.1,
                        confidence=1.0,
                    )
                ],
            }
        )
    else:
        d = inspect_bundle(FIXTURES / "mig02-multi-review")
        assert d.envelope
        groups = timeline_groups(d, d.envelope.sources[0].view_id, road, ())
        groups = tuple(
            replace(
                g,
                order_unresolved=kind == "unresolved",
                rows=tuple(replace(r, needs_review=kind == "needs_review") for r in g.rows),
            )
            for g in groups
        )
        panels = {road: ViewPanel(groups, (), ())}
    report = driver_report.model_copy(update={"facts": facts})
    a = Alignment("b" * 64, road, 0.0, 0.5, "reviewer_estimated", "Synthetic reviewer", "fixture")
    contacts = [t.contact for t in driver_panels(report, panels, (a,))["b" * 64].roads[0].timings]
    expected = {
        "obscured": "contact possible, obscured",
        "overturned": "vehicle overturned",
        "needs_review": "Needs review",
        "unresolved": "Order not determined",
    }[kind]
    assert any(expected in (c.label + c.review_status) for c in contacts)
