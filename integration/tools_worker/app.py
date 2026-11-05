"""Local reconstruction API, used only by the IncidentDesk server.

Starlette routes and pure ASGI middleware follow the official routing/middleware
documentation. The launcher, rather than this factory, owns the loopback listener.
"""

from hmac import compare_digest
from pathlib import Path
import re

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route


class LocalAccess:
    """Reject remote clients and require a token even for health and unknown URLs."""

    def __init__(self, app, token):
        self.app = app
        self.expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return
        peer = scope.get("client")
        credentials = [value for key, value in scope["headers"] if key.lower() == b"authorization"]
        if peer is None or peer[0] != "127.0.0.1":
            response = JSONResponse({"error": "Local access required"}, status_code=403)
        elif len(credentials) != 1 or not compare_digest(credentials[0], self.expected):
            response = JSONResponse({"error": "Authentication required"}, status_code=401)
        else:
            async def no_cache(message):
                if message["type"] == "http.response.start":
                    message.setdefault("headers", []).append((b"cache-control", b"no-store"))
                await send(message)

            await self.app(scope, receive, no_cache)
            return
        response.headers["Cache-Control"] = "no-store"
        await response(scope, receive, send)


def create_app(cases_root: Path, token: str) -> Starlette:
    """Create an authenticated worker; never discover tokens or cases implicitly."""
    if not token or not token.strip() or any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise ValueError("Configure a nonempty printable local token")
    if not cases_root.is_absolute() or cases_root.is_symlink() or not cases_root.is_dir():
        raise ValueError("Configure an existing absolute cases directory without links")
    root = cases_root.resolve(strict=True)

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def selected_run(request):
        case_id = request.path_params["case_id"]
        run_id = request.path_params["run_id"]
        try:
            case = confined_child(root, case_id)
            # A case containing any link is not a writable evidence workspace.
            # This also rejects dangling links and linked output directories.
            if any(path.is_symlink() for path in case.rglob("*")):
                raise ValueError("Linked case")
            run = confined_child(case / "analysis" / "reconstruction", run_id)
            if not (run / "manifest.json").is_file():
                raise ValueError("Missing run")
        except (ValueError, OSError):
            return JSONResponse({"error": "Case or run unavailable"}, status_code=404)
        return JSONResponse({"case_id": case_id, "run_id": run_id})

    return Starlette(
        routes=[Route("/health", health), Route("/cases/{case_id}/runs/{run_id}", selected_run)],
        middleware=[Middleware(LocalAccess, token=token)],
    )


def confined_child(root: Path, identifier: str) -> Path:
    """IDs are single path components, never paths; links are refused, not followed."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identifier):
        raise ValueError("Invalid identifier")
    path = root / identifier
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Unavailable directory")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("Outside root")
    return path
