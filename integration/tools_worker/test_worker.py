"""Worker HTTP boundary tests; run in the reconstruction WSL environment."""

import asyncio
import shutil
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


def request(app, path, token="test-local-token", client_host="127.0.0.1"):
    async def run():
        transport = httpx.ASGITransport(app=app, client=(client_host, 40000))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            headers = {} if token is None else {"Authorization": f"Bearer {token}"}
            return await client.get(path, headers=headers)

    return asyncio.run(run())


def fixture_cases(tmp_path):
    source = ROOT / "contracts/evidence-v1/fixtures/mig02-multi-review/mig02-multi-review"
    destination = tmp_path / "cases"
    shutil.copytree(source, destination / source.name)
    return destination


def test_every_worker_request_requires_token_and_loopback(tmp_path):
    from integration.tools_worker.app import create_app

    app = create_app(fixture_cases(tmp_path), "test-local-token")
    assert request(app, "/health", token=None).status_code == 401
    assert request(app, "/health", token="wrong").status_code == 401
    assert request(app, "/health", client_host="192.0.2.1").status_code == 403
    response = request(app, "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "access-control-allow-origin" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_selected_fixture_run_and_unknown_identifiers(tmp_path):
    from integration.tools_worker.app import create_app

    app = create_app(fixture_cases(tmp_path), "test-local-token")
    selected = "/cases/mig02-multi-review/runs/week8-incident"
    response = request(app, selected)
    assert response.status_code == 200
    assert response.json() == {"case_id": "mig02-multi-review", "run_id": "week8-incident"}
    assert request(app, "/cases/missing/runs/week8-incident").status_code == 404
    assert request(app, "/cases/mig02-multi-review/runs/missing").status_code == 404


@pytest.mark.parametrize("identifier", ["..", ".", "%2E%2E", "%2Ftmp", "C:%5Ccases", "bad%5Cid", "bad%2Fid"])
@pytest.mark.parametrize("target", ["case", "run"])
def test_browser_paths_are_not_case_or_run_ids(tmp_path, identifier, target):
    from integration.tools_worker.app import create_app

    app = create_app(fixture_cases(tmp_path), "test-local-token")
    case = identifier if target == "case" else "mig02-multi-review"
    run = identifier if target == "run" else "week8-incident"
    response = request(app, f"/cases/{case}/runs/{run}")
    assert response.status_code in {404, 405}
    assert str(tmp_path) not in response.text


@pytest.mark.parametrize("location", ["case", "run", "output", "dangling"])
def test_case_links_and_output_links_are_refused(tmp_path, location):
    from integration.tools_worker.app import create_app

    cases = fixture_cases(tmp_path)
    case = cases / "mig02-multi-review"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("untouched")
    if location == "case":
        shutil.move(case, outside / "case")
        case.symlink_to(outside / "case", target_is_directory=True)
    elif location == "run":
        run = case / "analysis/reconstruction/week8-incident"
        shutil.move(run, outside / "run")
        run.symlink_to(outside / "run", target_is_directory=True)
    else:
        (case / "linked-output").symlink_to(outside if location == "output" else outside / "missing", target_is_directory=True)
    app = create_app(cases, "test-local-token")
    response = request(app, "/cases/mig02-multi-review/runs/week8-incident")
    assert response.status_code == 404
    assert (outside / "sentinel").read_text() == "untouched"


def test_worker_refuses_unconfigured_secret_and_root(tmp_path):
    from integration.tools_worker.app import create_app

    for token in ("", " ", "line\nbreak", "unicode-\u00e9"):
        with pytest.raises(ValueError):
            create_app(tmp_path, token)
    with pytest.raises(ValueError):
        create_app(Path("relative"), "test-local-token")
