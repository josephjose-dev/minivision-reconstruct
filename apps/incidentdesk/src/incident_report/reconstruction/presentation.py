"""Read-only web context; never mutates Report or its cited storyline."""

from dataclasses import dataclass
from typing import Any

from incident_report.domain import Report

from .config import ReconstructionSettings
from .paths import list_bundles
from .store import Attachment, Workspace
from .timeline import MISSING_LABELS, TimelineGroup, timeline_groups
from .tools import tool_links


@dataclass(frozen=True)
class ViewPanel:
    groups: tuple[TimelineGroup, ...]
    notices: tuple[str, ...]
    links: tuple[Attachment, ...]
    tool_selections: tuple[str, ...] = ()


def context(workspace: Workspace, report: Report, settings: ReconstructionSettings) -> dict[str, Any]:
    if not settings.enabled:
        return {}
    current = workspace.current(report.run_id)
    panels = {}
    for view in report.views:
        links = tuple(link for link in current if link.view_sha256 == view.sha256)
        groups = list(timeline_groups(None, "", view.sha256, report.storyline))
        notices = []
        selections = []
        for link in links:
            decision = workspace.decision(link.import_id)
            if decision.envelope:
                source = next(s for s in decision.envelope.sources if s.view_id == link.source_view_id)
                selections.append(
                    f"Case: {link.producer_case_id}; tracking run: {source.tracking_run}; tracks revision: {source.track_revision}; calibration: {source.calibration_revision}; reconstruction run: {source.reconstruction_run}; incident run: {source.incident_run}; review revision: {source.review_revision}"
                )
            groups.extend(timeline_groups(decision, link.source_view_id, view.sha256, ()))
            for code in decision.missing_inputs:
                notices.append("Reconstruction could not assess this view: " + MISSING_LABELS.get(code, code))
            if decision.provenance_state != "verified":
                notices.append("Reconstruction provenance is incomplete; review the imported evidence before use.")
        groups.sort(
            key=lambda group: min(
                (r.source_time for r in group.rows if r.source_time is not None), default=float("inf")
            )
        )
        panels[view.sha256] = ViewPanel(tuple(groups), tuple(dict.fromkeys(notices)), links, tuple(selections))
    return {
        "reconstruction": panels,
        "reconstruction_tools": tool_links(),
        "reconstruction_bundles": list_bundles(settings.evidence_exports_root)
        if settings.evidence_exports_root
        else (),
    }
