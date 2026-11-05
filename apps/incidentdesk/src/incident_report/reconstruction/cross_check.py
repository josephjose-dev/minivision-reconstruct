"""Read-only same-view comparisons; never a source of report facts or fault inputs."""

from dataclasses import dataclass, replace

from incident_report.evidence_import.models import ImportDecision
from incident_report.evidence_import.payloads import EventFields
from incident_report.facts import OverviewFacts

from .timeline import TimelineRow, timeline_groups

CONTACT_KINDS = {"vehicle_contact_vehicle", "vehicle_struck_pedestrian", "contact_other"}


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
    """Mappings must be latest, current-import reviewer mappings in this view only."""
    records = tuple(r for r in decision.records if r.view_id == source_view)
    candidates = {
        r.record_id for r in records if isinstance(r.data, EventFields) and r.data.event_type == "collision_candidate"
    }
    assessments = [a for a in facts.incident_assessments if a.view_id == view_sha] if facts else []
    assessment = assessments[0] if len(assessments) == 1 else None
    contacts = (
        [c for c in facts.collision_observations if c.view_id == view_sha and c.kind in CONTACT_KINDS] if facts else []
    )
    times = (
        (assessment.contact_interval_start_seconds, assessment.contact_interval_end_seconds)
        if assessment
        and assessment.contact_interval_start_seconds is not None
        and assessment.contact_interval_end_seconds is not None
        else tuple(c.timestamp_seconds for c in contacts)
    )
    rows = [
        row
        for group in timeline_groups(decision, source_view, view_sha, ())
        for row in group.rows
        if row.key in candidates
    ]

    def result(row: TimelineRow | None, state: str, reason: str, delta: float | None = None) -> Comparison:
        return Comparison(
            "Contact time",
            state,
            reason,
            view_sha,
            row.source_time if row else None,
            row.source_frame if row else None,
            times,
            row.review_status if row else "No candidate supplied",
            delta,
        )

    if decision.missing_inputs:
        return (result(None, "reconstruction_unavailable", "; ".join(decision.missing_inputs)),) + _motion_context(
            decision, source_view, view_sha, facts, mappings, rows
        )
    observed = bool(assessment and assessment.contact_state == "contact_observed") or bool(contacts)
    if not rows:
        return (
            result(
                None, "tracker_miss" if observed else "cannot_compare", "No reconstruction collision candidate supplied"
            ),
        )
    output = []
    for row in rows:
        if row.rejected or row.source_time is None or row.source_frame is None:
            output.append(result(row, "cannot_compare", "Candidate rejected or effective source time/frame unknown"))
        elif len(row.track_refs) != 2 or any(ref not in mappings for ref in row.track_refs):
            output.append(result(row, "cannot_compare", "Tracks need same-view reviewer mappings"))
        elif assessment and assessment.contact_state in {"contact_possible_obscured", "cannot_assess"}:
            output.append(result(row, "cannot_compare", assessment.contact_state))
        elif assessment and assessment.contact_state == "no_contact_observed":
            output.append(result(row, "model_miss", "Video analysis did not report contact"))
        elif observed and times:
            if assessment and assessment.contact_interval_start_seconds is not None:
                low, high = times
                agrees = low <= row.source_time <= high
                delta = row.source_time - (low if row.source_time < low else high)
            else:
                # Exact explicit timestamps only. No FPS-based tolerance is invented.
                agrees = row.source_time in times
                delta = min((row.source_time - t for t in times), key=abs)
            output.append(
                result(
                    row,
                    "agree" if agrees else "disagree_time",
                    "Reconstruction peak and video analysis contact times",
                    None if agrees else delta,
                )
            )
        else:
            output.append(result(row, "cannot_compare", "No explicit video analysis contact timing"))
    for row in rows:
        base = result(row, "cannot_compare", "No unique matching contact or current party mapping")
        matching = [c for c in contacts if c.timestamp_seconds == row.source_time]
        if not matching and len(contacts) == 1:
            matching = contacts
        pair = [mappings.get(ref) for ref in row.track_refs]
        if (
            not row.rejected
            and row.source_time is not None
            and len(pair) == 2
            and all(pair)
            and len(set(pair)) == 2
            and len(matching) == 1
        ):
            contact = matching[0]

            def code(name: str) -> str | None:
                parties = [p for p in facts.parties if p.view_id == view_sha and p.description == name] if facts else []
                if len(parties) != 1 or not parties[0].party_code:
                    return None
                value = parties[0].party_code
                return (
                    value
                    if facts and sum(p.view_id == view_sha and p.party_code == value for p in facts.parties) == 1
                    else None
                )

            video_pair = [code(contact.subject), code(contact.other_party)]
            known = all(video_pair) and len(set(video_pair)) == 2
            base = replace(
                base,
                state=("agree" if set(pair) == set(video_pair) else "disagree_parties") if known else "cannot_compare",
                reason=f"Reconstruction party codes: {pair}; video analysis: {contact.subject} / {contact.other_party}",
                video_times=(contact.timestamp_seconds,),
            )
        output.append(replace(base, item="Parties in contact"))
    return tuple(output) + _motion_context(decision, source_view, view_sha, facts, mappings, rows)


MOTION = {"moving": "moving", "stopped_in_lane": "stopped", "parked_at_kerb": "stopped"}


def _motion_context(
    decision: ImportDecision,
    source_view: str,
    view_sha: str,
    facts: OverviewFacts | None,
    mappings: dict[str, str],
    candidates: list[TimelineRow],
) -> tuple[Comparison, ...]:
    if facts is None:
        return ()
    kinds = {
        r.record_id: r.data.event_type
        for r in decision.records
        if r.view_id == source_view and isinstance(r.data, EventFields)
    }
    movements = [
        r
        for g in timeline_groups(decision, source_view, view_sha, ())
        for r in g.rows
        if kinds.get(r.key) in {"first_observed", "last_observed", "stop", "start"}
        and not r.rejected
        and r.source_time is not None
        and r.source_frame is not None
    ]
    contact_refs = {ref for r in candidates if not r.rejected for ref in r.track_refs}
    output = []
    for party in facts.parties:
        if party.view_id != view_sha or not party.party_code:
            continue
        if sum(p.view_id == view_sha and p.party_code == party.party_code for p in facts.parties) != 1:
            continue
        refs = [ref for ref in contact_refs if mappings.get(ref) == party.party_code]
        events = [r for r in movements if len(refs) == 1 and refs[0] in r.track_refs]
        first = [r for r in events if kinds[r.key] == "first_observed"]
        last = [r for r in events if kinds[r.key] == "last_observed"]
        contacts = [
            r
            for r in candidates
            if not r.rejected and any(ref in r.track_refs for ref in refs) and r.source_time is not None
        ]
        late = next(
            (
                r
                for r in first
                if any(
                    r.source_time is not None and c.source_time is not None and r.source_time >= c.source_time
                    for c in contacts
                )
            ),
            None,
        )
        missing = any("calibration" in c or "timestamp" in c for c in decision.missing_inputs)
        if refs and (late or missing):
            citation = late or (contacts[0] if contacts else None)
            output.append(
                Comparison(
                    "Pre-contact context",
                    "cannot_compare",
                    f"Reconstruction lacks pre-contact context for {party.description}"
                    + (": " + "; ".join(decision.missing_inputs) if missing else ": first seen at or after contact"),
                    view_sha,
                    citation.source_time if citation else None,
                    citation.source_frame if citation else None,
                    tuple(c.source_time for c in contacts if c.source_time is not None),
                    citation.review_status if citation else "Review status unavailable",
                )
            )
        for fact in facts.structured_facts:
            if (
                fact.view_id != view_sha
                or fact.subject != party.description
                or fact.field != "motion_state_before_contact"
            ):
                continue
            time = fact.timestamp_seconds
            boundaries = (
                len(first) == 1
                and len(last) == 1
                and first[0].source_time is not None
                and last[0].source_time is not None
                and first[0].source_time <= time <= last[0].source_time
            )
            transitions = [
                r
                for r in events
                if kinds[r.key] in {"stop", "start"} and r.source_time is not None and r.source_time <= time
            ]
            transitions.sort(key=lambda r: r.source_time or 0)
            cited = transitions[-1] if transitions else None
            states = {kinds[r.key] for r in transitions if cited and r.source_time == cited.source_time}
            actual = ("stopped" if kinds[cited.key] == "stop" else "moving") if cited and len(states) == 1 else None
            valid = (
                boundaries
                and not decision.missing_inputs
                and len(refs) == 1
                and actual is not None
                and fact.value in MOTION
            )
            state = ("agree" if actual == MOTION.get(fact.value) else "disagree_motion") if valid else "cannot_compare"
            output.append(
                Comparison(
                    "Motion",
                    state,
                    f"{party.description}: reconstruction {actual or 'unknown'}; video analysis {fact.value}",
                    view_sha,
                    cited.source_time if cited else None,
                    cited.source_frame if cited else None,
                    (time,),
                    cited.review_status if cited else "Review status unavailable",
                )
            )
    return tuple(output)
