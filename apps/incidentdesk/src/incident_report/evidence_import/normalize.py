"""Validate the producer graph and retain originals beside proposal-only normalized records."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .models import Envelope, NormalizedRecord, SourceBinding
from .reader import InvalidBundle, safe_path

STATUSES = {"PROPOSED_BY_SYSTEM", "CONFIRMED_BY_REVIEWER", "REJECTED_BY_REVIEWER", "MODIFIED_BY_REVIEWER"}
STATES = {
    "observed",
    "lost",
    "recovered",
    "interpolated",
    "estimated",
    "reviewer",
    "tentative",
    "confirmed",
    "deleted",
    "unavailable",
}


def identity(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def normalize(
    envelope: Envelope, parsed: dict[str, list[dict[str, Any]]], hashes: dict[str, str], issues: list[str]
) -> tuple[NormalizedRecord, ...]:
    """Hash closure includes every supplied manifest, even older reviewed revisions."""
    if not envelope.sources:
        issues.append("missing source bindings")
    if len({source.view_id for source in envelope.sources}) != len(envelope.sources):
        raise InvalidBundle("duplicate view binding")
    by_hash = {digest: name for name, digest in hashes.items()}
    for source in envelope.sources:
        by_hash[source.original_video_sha256] = "original-video-binding-only"
    for path, documents in parsed.items():
        for document in documents:
            _closure(path, document, hashes, by_hash, issues)
    records: list[NormalizedRecord] = []
    for source in envelope.sources:
        records.extend(_source(envelope, source, parsed, hashes, issues))
    ids = [record.record_id for record in records]
    if len(ids) != len(set(ids)):
        raise InvalidBundle("duplicate normalized record identity")
    return tuple(records)


def _closure(
    path: str, document: dict[str, Any], hashes: dict[str, str], by_hash: dict[str, str], issues: list[str]
) -> None:
    for artifact in document.get("artifacts", []):
        child = safe_path(artifact["filename"])
        target = (PurePosixPath(path).parent / child).as_posix()
        if target not in hashes:
            issues.append(f"missing upstream artifact: {target}")
        elif hashes[target] != artifact["sha256"]:
            raise InvalidBundle(f"producer artifact hash mismatch: {target}")
    for key, value in document.items():
        # Original video is bound by digest, intentionally not copied into the JSON evidence package.
        if key.endswith("_sha256") and value is not None and key not in {"source_video_sha256", "revision_sha256"}:
            if not isinstance(value, str) or len(value) != 64:
                raise InvalidBundle("invalid producer digest")
            if value not in by_hash:
                issues.append(f"missing upstream hash: {path}:{key}")
    if document.get("rule_source") is not None:
        raise InvalidBundle("producer rule_source must remain null")


def _source(
    envelope: Envelope,
    source: SourceBinding,
    parsed: dict[str, list[dict[str, Any]]],
    hashes: dict[str, str],
    issues: list[str],
) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    prefix = (envelope.producer, envelope.case_id, source.view_id, source.tracking_run, source.track_revision)

    def track(track_id: int) -> str:
        if type(track_id) is not int or track_id < 1:
            raise InvalidBundle("invalid track ID")
        return identity(*prefix, track_id)

    def load(path: str) -> list[dict[str, Any]]:
        safe_path(path)
        if path not in parsed:
            issues.append(f"missing upstream JSON: {path}")
        return parsed.get(path, [])

    def manifest(path: str, run: str) -> dict[str, Any]:
        documents = load(path)
        if len(documents) != 1:
            issues.append(f"missing or ambiguous manifest: {path}")
            return {}
        result = documents[0]
        if (
            result.get("case_id") != envelope.case_id
            or result.get("run_id") != run
            or result.get("schema_version") != "1.0"
        ):
            raise InvalidBundle("manifest identity or schema mismatch")
        return result

    def add(kind: Any, path: str, original: dict[str, Any], token: object, **values: Any) -> None:
        records.append(
            NormalizedRecord(
                record_id=identity(*prefix, path, token),
                kind=kind,
                view_id=source.view_id,
                artifact_path=path,
                original=original,
                **values,
            )
        )

    reconstruction = manifest(source.reconstruction_manifest, source.reconstruction_run)
    movement = manifest(source.movement_manifest, source.movement_run)
    incident = manifest(source.incident_manifest, source.incident_run)
    reviewed = manifest(source.reviewed_manifest, source.incident_run)
    checks = (
        (reconstruction, "source_video_sha256", source.original_video_sha256),
        (reconstruction, "tracking_run", source.tracking_run),
        (reconstruction, "track_revision", source.track_revision),
        (reconstruction, "calibration_revision", source.calibration_revision),
        (movement, "reconstruction_run", source.reconstruction_run),
        (movement, "source_reconstruction_manifest_sha256", hashes.get(source.reconstruction_manifest)),
        (incident, "movement_run", source.movement_run),
        (incident, "source_movement_manifest_sha256", hashes.get(source.movement_manifest)),
        (reviewed, "source_incident_manifest_sha256", hashes.get(source.incident_manifest)),
        (reviewed, "review_revision", source.review_revision),
    )
    for document, key, expected in checks:
        if document and document.get(key) != expected:
            raise InvalidBundle(f"source binding mismatch: {key}")
    rec_root = PurePosixPath(source.reconstruction_manifest).parent
    mov_root = PurePosixPath(source.movement_manifest).parent
    inc_root = PurePosixPath(source.incident_manifest).parent
    rev_root = PurePosixPath(source.reviewed_manifest).parent
    timestamps = load(str(rec_root / "source_frames.jsonl"))
    time_by_frame: dict[int, dict[str, Any]] = {}
    frame_by_time: dict[float, int] = {}
    for row in timestamps:
        frame, time = row["source_frame"], row["source_time"]
        if (
            type(frame) is not int
            or frame < 0
            or not isinstance(time, (float, int))
            or time < 0
            or not row["timestamp_source"]
        ):
            raise InvalidBundle("invalid source timestamp")
        if frame in time_by_frame or time in frame_by_time:
            raise InvalidBundle("ambiguous source timestamp mapping")
        time_by_frame[frame] = row
        frame_by_time[time] = frame
    if not timestamps:
        issues.append("missing_input: no source timestamps")

    def citation(frame: Any, time: Any) -> dict[str, Any]:
        row = time_by_frame.get(frame)
        if row is None or row["source_time"] != time:
            issues.append("source frame/time unresolved")
            return {"needs_review": True}
        return {"source_frame": frame, "source_time": time, "timestamp_provenance": row["timestamp_source"]}

    add("source_binding", source.reconstruction_manifest, source.model_dump(mode="json"), "binding")
    for row in timestamps:
        add(
            "source_binding",
            str(rec_root / "source_frames.jsonl"),
            row,
            row["source_frame"],
            **citation(row["source_frame"], row["source_time"]),
        )
    for name in ("observations.jsonl", "replay_frames.jsonl"):
        path = str(rec_root / name)
        for index, row in enumerate(load(path)):
            cite = citation(row["source_frame"], row["source_time"])
            if name == "observations.jsonl":
                if row["state"] not in STATES:
                    raise InvalidBundle("unknown track state")
                add("track_reference", path, row, index, track_refs=(track(row["track_id"]),), **cite)
            else:
                add("source_binding", path, row, index, **cite)
    if movement and (movement.get("unit"), movement.get("calibration_mode")) not in {
        ("m", "metric"),
        ("relative_units", "non_metric"),
    }:
        raise InvalidBundle("calibration units mismatch")
    for name in ("smoothed.jsonl", "movement_observations.jsonl"):
        path = str(mov_root / name)
        for index, row in enumerate(load(path)):
            if movement and row["unit"] != movement.get("unit"):
                raise InvalidBundle("mixed geometry units")
            add(
                "geometry",
                path,
                row,
                index,
                track_refs=(track(row["track_id"]),),
                **citation(row["source_frame"], row.get("source_time", row.get("timestamp_seconds"))),
            )
    sequence_path = str(mov_root / "sequence.json")
    for document in load(sequence_path):
        for row in document["entries"]:
            add("sequence", sequence_path, row, row["event_id"], track_refs=tuple(track(t) for t in row["track_ids"]))

    originals: dict[str, dict[str, Any]] = {}
    original_assessments: dict[str, dict[str, Any]] = {}
    for row in load(str(inc_root / "events.jsonl")):
        if row["event_id"] in originals:
            raise InvalidBundle("duplicate event ID")
        originals[row["event_id"]] = row
    for row in load(str(inc_root / "assessments.jsonl")):
        if row["assessment_id"] in original_assessments or row["rule_source"] is not None:
            raise InvalidBundle("invalid assessment")
        original_assessments[row["assessment_id"]] = row
    if not originals:
        issues.append("missing_input: no incident candidates")

    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    revision_hash = reviewed.get("review_revision_sha256")
    expected_revision = source.review_revision
    visited: set[str] = set()
    latest_loaded = False
    while revision_hash:
        if revision_hash in visited:
            raise InvalidBundle("cyclic review chain")
        visited.add(revision_hash)
        candidates = [p for p, h in hashes.items() if h == revision_hash]
        if not candidates:
            issues.append("missing upstream review revision")
            break
        revision_path = candidates[0]
        revision_docs = load(revision_path)
        if len(revision_docs) != 1:
            raise InvalidBundle("invalid review revision")
        revision = revision_docs[0]
        if revision["revision_id"] != expected_revision:
            raise InvalidBundle("review revision binding mismatch")
        if not latest_loaded:
            latest_loaded = True
            for decision in revision["document"]["decisions"]:
                decision_key = (decision["target_kind"], decision["target_id"])
                if decision_key in decisions:
                    raise InvalidBundle("duplicate review decision")
                decisions[decision_key] = decision
        previous = revision["previous_sha256"]
        if previous == hashes.get(source.incident_manifest):
            break
        revision_hash = previous
        # IDs are producer revision-NNN; verify backwards order rather than trusting arbitrary linked JSON.
        number = int(expected_revision.removeprefix("revision-"))
        if number <= 1:
            raise InvalidBundle("review chain does not terminate at incident manifest")
        expected_revision = f"revision-{number - 1:03d}"
    if source.review_revision == "initial" and revision_hash is not None:
        raise InvalidBundle("initial review cannot name a revision")
    if source.review_revision != "initial" and reviewed and not revision_hash:
        issues.append("missing upstream review revision")
    review_available = source.review_revision == "initial" or latest_loaded

    def check_frames(proposal: dict[str, Any]) -> None:
        for field in ("start_frame", "peak_frame", "end_frame"):
            if field in proposal:
                citation(proposal[field], proposal[field.replace("frame", "time")])
        for collection in ("signals", "supporting_evidence", "counterevidence"):
            for signal in proposal.get(collection, []):
                for frame in signal["source_frames"]:
                    if frame not in time_by_frame:
                        issues.append("supporting evidence frame unresolved")

    for proposal in (*originals.values(), *original_assessments.values()):
        check_frames(proposal)

    statuses: dict[str, str] = {}
    seen_events: set[str] = set()
    path = str(rev_root / "reviewed_events.jsonl")
    for row in load(path):
        proposal = row["proposal"]
        event_id = proposal["event_id"]
        if event_id in seen_events or (event_id in originals and originals[event_id] != proposal):
            raise InvalidBundle("reviewed event does not preserve original proposal")
        if event_id not in originals:
            issues.append("missing original event proposal")
        seen_events.add(event_id)
        decision = decisions.get(("event", event_id)) if review_available else row["decision"]
        expected_status = _review_status(decision)
        if row["status"] not in STATUSES or (
            review_available and (row["status"] != expected_status or row["decision"] != decision)
        ):
            raise InvalidBundle("event review overlay mismatch")
        statuses[event_id] = row["status"]
        if movement and proposal["unit"] != movement.get("unit"):
            raise InvalidBundle("event units mismatch")
        refs = tuple(track(t) for t in proposal["track_ids"])
        add(
            "event_proposal",
            path,
            proposal,
            event_id,
            track_refs=refs,
            producer_status=row["status"],
            **citation(proposal["peak_frame"], proposal["peak_time"]),
        )
        effective_time = decision.get("modified_peak_time") if decision else None
        effective_time = proposal["peak_time"] if effective_time is None else effective_time
        effective_location = decision.get("modified_location") if decision else None
        effective_location = proposal["location"] if effective_location is None else effective_location
        if row["peak_time"] != effective_time or row["location"] != effective_location:
            raise InvalidBundle("effective event value inconsistent with review")
        if decision:
            frame = frame_by_time.get(effective_time)
            add(
                "review_overlay",
                path,
                decision,
                event_id + "-review",
                effective={
                    "peak_time": effective_time,
                    "location": effective_location,
                    "reviewer_authenticated": False,
                },
                track_refs=refs,
                producer_status=row["status"],
                **citation(frame, effective_time),
            )
    if seen_events != originals.keys():
        issues.append("missing reviewed events")
    for event_id in originals.keys() - seen_events:
        proposal = originals[event_id]
        add(
            "event_proposal",
            str(inc_root / "events.jsonl"),
            proposal,
            event_id,
            track_refs=tuple(track(t) for t in proposal["track_ids"]),
            needs_review=True,
        )
    seen_assessments: set[str] = set()
    path = str(rev_root / "reviewed_assessments.jsonl")
    for row in load(path):
        proposal = row["proposal"]
        assessment_id = proposal["assessment_id"]
        if assessment_id in seen_assessments or (
            assessment_id in original_assessments and original_assessments[assessment_id] != proposal
        ):
            raise InvalidBundle("reviewed assessment does not preserve original proposal")
        if assessment_id not in original_assessments:
            issues.append("missing original assessment proposal")
        seen_assessments.add(assessment_id)
        decision = decisions.get(("assessment", assessment_id)) if review_available else row["decision"]
        parent = statuses.get(proposal["event_id"])
        if row["status"] not in STATUSES or (
            review_available
            and (
                row["status"] != _review_status(decision)
                or row["decision"] != decision
                or (parent is not None and row["event_status"] != parent)
            )
        ):
            raise InvalidBundle("assessment or parent status mismatch")
        if parent is None:
            issues.append("assessment parent event missing")
        effective = {"outcome": row["outcome"], "contributing_track_ids": row["contributing_track_ids"]}
        for key, modification in (
            ("outcome", "modified_outcome"),
            ("contributing_track_ids", "modified_contributing_track_ids"),
        ):
            expected = decision.get(modification) if decision else None
            if effective[key] != (proposal[key] if expected is None else expected):
                raise InvalidBundle("assessment effective value mismatch")
        add(
            "assessment",
            path,
            proposal,
            assessment_id,
            effective=effective,
            producer_status=row["status"],
            parent_status=parent,
            track_refs=tuple(track(t) for t in proposal["involved_track_ids"]),
            needs_review=True,
        )
        if decision:
            add(
                "review_overlay",
                path,
                decision,
                assessment_id + "-review",
                effective=effective,
                producer_status=row["status"],
                parent_status=parent,
                needs_review=True,
            )
    if seen_assessments != original_assessments.keys():
        issues.append("missing reviewed assessments")
    for assessment_id in original_assessments.keys() - seen_assessments:
        proposal = original_assessments[assessment_id]
        add(
            "assessment",
            str(inc_root / "assessments.jsonl"),
            proposal,
            assessment_id,
            track_refs=tuple(track(t) for t in proposal["involved_track_ids"]),
            needs_review=True,
        )
    return records


def _review_status(decision: dict[str, Any] | None) -> str:
    if decision is None:
        return "PROPOSED_BY_SYSTEM"
    action = decision["action"]
    if action not in {"confirm", "reject", "modify"}:
        raise InvalidBundle("unknown review action")
    return {"confirm": "CONFIRMED_BY_REVIEWER", "reject": "REJECTED_BY_REVIEWER", "modify": "MODIFIED_BY_REVIEWER"}[
        action
    ]
