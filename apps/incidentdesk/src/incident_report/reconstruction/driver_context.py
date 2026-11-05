"""Read-only interior intervals; never an input to driver or collision rules."""

from dataclasses import dataclass

from incident_report.domain import Report, Role
from incident_report.facts import DriverObservation
from incident_report.rules.driver import DriverAssessment


@dataclass(frozen=True)
class DriverPanel:
    observations: tuple[DriverObservation, ...]
    assessments: tuple[DriverAssessment, ...]


def driver_panels(report: Report) -> dict[str, DriverPanel]:
    return {
        view.sha256: DriverPanel(
            tuple(o for o in report.facts.driver_observations if o.view_id == view.sha256) if report.facts else (),
            tuple(a for a in report.driver_assessments if any(c.view_id == view.sha256 for c in a.cited_facts)),
        )
        for view in report.views
        if view.role == Role.INTERIOR
    }
