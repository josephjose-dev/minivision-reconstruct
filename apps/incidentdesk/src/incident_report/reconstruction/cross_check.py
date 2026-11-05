"""Read-only same-view comparisons; never a source of report facts or fault inputs."""

from dataclasses import dataclass

from incident_report.evidence_import.models import ImportDecision
from incident_report.evidence_import.payloads import EventFields
from incident_report.facts import OverviewFacts

from .timeline import timeline_groups


@dataclass(frozen=True)
class Comparison:
    item: str
    state: str
    reason: str
    view_id: str
    producer_time: float | None
    producer_frame: int | None
    video_times: tuple[float, ...]
    review_status: str
    difference_seconds: float | None = None


def compare_view(
    decision: ImportDecision,
    source_view: str,
    view_sha: str,
    facts: OverviewFacts | None,
    mappings: dict[str, str],
) -> tuple[Comparison, ...]:
    candidates = {
        r.record_id
        for r in decision.records
        if r.view_id == source_view and isinstance(r.data, EventFields) and r.data.event_type == "collision_candidate"
    }
    return tuple(
        Comparison(
            "Contact time",
            "cannot_compare",
            "Tracks need same-view reviewer mappings",
            view_sha,
            row.source_time,
            row.source_frame,
            (),
            row.review_status,
        )
        for group in timeline_groups(decision, source_view, view_sha, ())
        for row in group.rows
        if row.key in candidates
    )
