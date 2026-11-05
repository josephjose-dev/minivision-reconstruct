"""Native producer tools: existing report access, immutable attached IDs, CSRF writes."""

import hashlib
import os
import secrets
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from incident_report.domain import Role
from incident_report.reconstruction.config import ReconstructionSettings
from incident_report.reconstruction.database import local_database
from incident_report.reconstruction.native_client import ToolsUnavailable, ToolsWorker
from incident_report.reconstruction.store import Workspace
from incident_report.runlog import RunLog
from incident_report.web.access import _check_origin, _csrf_token
from incident_report.web.body_limit import BodyTooLargeError, read_limited_body
from incident_report.web.review import accessible_report
from incident_report.web.templating import build_environment


def native_enabled() -> bool:
    value = os.environ.get("INCIDENTDESK_NATIVE_TOOLS", "false").strip().lower()
    if value not in {"false", "0", "true", "1", ""}:
        raise ValueError("INCIDENTDESK_NATIVE_TOOLS must be true or false")
    return value in {"true", "1"}


def track_action(fields: dict[str, str]) -> dict[str, Any]:
    action = fields.get("action", "")
    parameters = {
        "correct": ("track_id", "frame_number"),
        "add": ("track_id", "frame_number"),
        "create_track": ("new_track_id", "frame_number"),
        "delete_observation": ("track_id", "frame_number"),
        "delete_track": ("track_id",),
        "merge": ("primary_track_id", "secondary_track_id"),
        "split": ("track_id", "frame_number", "new_track_id"),
        "repair_gap": ("track_id", "start_frame", "end_frame"),
        "undo": (),
        "export": (),
    }
    if action not in parameters:
        raise ValueError("Choose a track review action.")
    payload: dict[str, Any] = {key: int(fields.get(key, "")) for key in parameters[action]}
    if action == "create_track":
        payload["track_id"] = payload.pop("new_track_id")
    if action in {"correct", "add", "create_track"}:
        if action != "correct" or fields.get("class_name"):
            payload["class_name"] = fields.get("class_name", "")
        if fields.get("bbox", "").strip():
            payload["bbox"] = [float(value) for value in fields["bbox"].split(",")]
    return {
        "action": action,
        "payload": payload,
        "reviewer": fields.get("reviewer", "").strip(),
        "reason": fields.get("reason", "").strip(),
    }


def install_native_tools(
    app: FastAPI, log: RunLog, error_page: Callable[[Request, int, str], Response], settings: ReconstructionSettings
) -> None:
    native_enabled()  # Invalid flag fails startup, even when reconstruction is off.
    templates = Jinja2Templates(env=build_environment())

    def audit_action(request: Request, run_id: uuid.UUID, link_id: uuid.UUID, body: dict[str, Any], stage: str) -> None:
        attribution = request.state.attribution
        log.audit.append(
            event_type="reconstruction",
            action=f"native.tracks.{stage}",
            actor="visitor",
            session_id=attribution.session_id,
            link_id=attribution.link_id,
            request_id=request.state.request_id,
            run_id=run_id,
            target_type="reconstruction_attachment",
            target_id=str(link_id),
            details={
                "operation": body["action"],
                "reviewer_sha256": hashlib.sha256(body["reviewer"].encode()).hexdigest(),
                "reason_sha256": hashlib.sha256(body["reason"].encode()).hexdigest(),
            },
        )

    def selection(request: Request, run_id: uuid.UUID, link_id: uuid.UUID) -> tuple[Any, Any]:
        if not native_enabled() or not settings.enabled:
            raise HTTPException(404, "Native tools are disabled.")
        if getattr(request.state, "attribution", None) is None:
            raise HTTPException(403, "Open a valid share link to use the tool.")
        run = accessible_report(log, request, run_id)
        if run.report is None:
            raise HTTPException(404, "Report unavailable.")
        with psycopg.connect(local_database(log.database_url)) as connection:
            workspace = Workspace(connection, settings)
            links = [item for item in workspace.current(run_id) if item.link_id == link_id]
            if not links or not any(
                view.sha256 == links[0].view_sha256 and view.role != Role.INTERIOR for view in run.report.views
            ):
                raise HTTPException(404, "Attached road-view selection unavailable.")
            link = links[0]
            decision = workspace.decision(link.import_id)
            if decision.envelope is None:
                raise HTTPException(404, "Re-import this evidence before opening tools.")
            source = next(item for item in decision.envelope.sources if item.view_id == link.source_view_id)
        return link, source

    @app.get("/reports/{run_id}/tools/{link_id}/tracks")
    @app.get("/reports/{run_id}/tools/{link_id}/tracks/frame")
    def tracks(request: Request, run_id: uuid.UUID, link_id: uuid.UUID, frame: int = 0) -> Response:
        link, source = selection(request, run_id, link_id)
        if frame < 0:
            raise HTTPException(422, "Choose a nonnegative source frame.")
        worker_path = f"/cases/{quote(link.producer_case_id, safe='')}/tracks/{quote(source.tracking_run, safe='')}"
        try:
            worker = ToolsWorker()
            if request.url.path.endswith("/frame"):
                body, content_type, status, headers = worker.exchange(f"{worker_path}/image?frame={frame}")
                return Response(
                    body, status_code=status, media_type=content_type, headers={**headers, "Cache-Control": "no-store"}
                )
            data = worker.json(f"{worker_path}?frame={frame}")
            return templates.TemplateResponse(
                request,
                "native_tracks.html",
                {
                    "data": data,
                    "frame": frame,
                    "base": str(request.url.path),
                    "run_id": run_id,
                    "csrf_token": _csrf_token(request),
                },
            )
        except (ToolsUnavailable, OSError, psycopg.Error):
            return error_page(request, 503, "Local tools are unavailable. Ask the owner to start the tools worker.")

    @app.post("/reports/{run_id}/tools/{link_id}/tracks")
    async def save_tracks(request: Request, run_id: uuid.UUID, link_id: uuid.UUID) -> Response:
        link, source = await run_in_threadpool(selection, request, run_id, link_id)
        if not _check_origin(request):
            return error_page(request, 403, "Cross-origin submission refused.")
        try:
            await read_limited_body(request, max_bytes=16 * 1024)
            form = await request.form(max_part_size=16 * 1024)
            fields = {key: value if isinstance(value, str) else "" for key, value in form.items()}
            if not secrets.compare_digest(fields.get("csrf_token", ""), _csrf_token(request)):
                return error_page(request, 403, "Invalid or missing CSRF token.")
            body = track_action(fields)
            if not body["reviewer"] or not body["reason"]:
                raise ValueError("Reviewer and reason are required.")
            path = f"/cases/{quote(link.producer_case_id, safe='')}/tracks/{quote(source.tracking_run, safe='')}"
            await run_in_threadpool(audit_action, request, run_id, link_id, body, "requested")
            await run_in_threadpool(ToolsWorker().json, path, body)
            try:
                await run_in_threadpool(audit_action, request, run_id, link_id, body, "saved")
            except psycopg.Error:
                return error_page(
                    request,
                    503,
                    "The action completed, but audit confirmation failed. Reload saved revisions; do not repeat the action.",
                )
        except BodyTooLargeError:
            return error_page(request, 413, "Request body exceeds maximum size limit.")
        except ToolsUnavailable:
            return error_page(
                request, 503, "The worker did not confirm completion. Inspect saved revisions before submitting again."
            )
        except ValueError:
            return error_page(request, 422, "Check the action fields, reviewer and reason.")
        except (OSError, psycopg.Error):
            return error_page(request, 503, "No save was started: local audit or evidence storage is unavailable.")
        return RedirectResponse(request.url.path, status_code=303)
