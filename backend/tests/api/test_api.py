"""The HTTP API, end to end against a throwaway database."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

import samay.api.app as api_module
from dbhelpers import EXAMPLES, GOLDEN, example
from samay import __version__, cli
from samay.api import create_app
from samay.io import json_report
from samay.io.json_bill import MAX_BYTES


@pytest.fixture
def client(db: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(db), raise_server_exceptions=False) as test_client:
        yield test_client


def cli_json(name: str, command: str) -> dict[str, Any]:
    out = io.StringIO()
    cli.main([command, str(EXAMPLES / name), "--format", "json"], out=out, err=io.StringIO())
    data: dict[str, Any] = json.loads(out.getvalue())
    return data


def post_run(client: TestClient, data: bytes, command: str = "reconcile") -> Any:
    return client.post(
        "/api/runs",
        params={"command": command},
        content=data,
        headers={"content-type": "application/json"},
    )


def no_json_numbers(value: object) -> bool:
    """Money is never a JSON number anywhere in a response (ids are not money)."""
    if isinstance(value, dict):
        return all(no_json_numbers(v) for k, v in value.items() if k not in ("run_id", "exit_code"))
    if isinstance(value, list):
        return all(no_json_numbers(v) for v in value)
    return isinstance(value, str | bool) or value is None


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


def test_validate_valid_bill_saves_nothing(client: TestClient) -> None:
    response = client.post("/api/validate", content=example("matching.json"))
    assert response.status_code == 200
    body = response.json()
    assert body == cli_json("matching.json", "validate")
    assert body["valid"] is True
    assert body["synthetic"] is True
    assert client.get("/api/runs").json() == {"runs": []}


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not json", "json-syntax"),
        (b'{"format": "samay.bill/1"}', None),
        (b"", None),
        (b"x" * (MAX_BYTES + 10), "too-large"),
    ],
)
@pytest.mark.parametrize("path", ["/api/validate", "/api/runs"])
def test_invalid_bill_is_422_with_every_error_and_saves_nothing(
    client: TestClient, path: str, data: bytes, code: str | None
) -> None:
    response = client.post(path, content=data)
    assert response.status_code == 422
    body = response.json()
    assert body["valid"] is False
    assert body["exit_code"] == "2"
    assert body["errors"]
    if code is not None:
        assert code in {error["code"] for error in body["errors"]}
    assert body["command"] == ("validate" if path == "/api/validate" else "reconcile")
    assert client.get("/api/runs").json() == {"runs": []}


def test_reconcile_with_differences_is_saved_and_not_an_error(client: TestClient) -> None:
    response = post_run(client, example("differing.json"))
    assert response.status_code == 201
    body = response.json()
    run = body["run"]
    assert body["document_was_new"] is True
    assert run["exit_code"] == 1
    assert run["outcome"] == "not-clean"
    assert "not an error" in run["outcome_text"]
    assert run["synthetic"] is True
    assert body["report"] == cli_json("differing.json", "reconcile")
    statuses = {line["status"] for line in body["report"]["reconciliation"]["lines"]}
    assert "DIFFERS" in statuses
    total = body["report"]["calculation"]["total"]
    assert run["totals"]["calculated"]["paise"] == total["paise"]
    assert no_json_numbers(body)


def test_clean_reconciliation(client: TestClient) -> None:
    run = post_run(client, example("matching.json")).json()["run"]
    assert (run["exit_code"], run["outcome"], run["explanation"]) == (0, "clean", "complete")
    assert run["totals"]["difference"] == {"paise": "0", "inr": "₹0.00"}


def test_missing_values_stay_null_never_zero(client: TestClient) -> None:
    body = post_run(client, example("missing-data.json")).json()
    run = body["run"]
    assert run["totals"]["calculated"] is None
    assert run["totals"]["difference"] is None
    assert body["report"]["calculation"]["total"]["value"] is None
    assert body["report"]["calculation"]["total"]["missing_reasons"]


def test_calculate_only(client: TestClient) -> None:
    run = post_run(client, example("pass-through.json"), "calculate").json()["run"]
    assert (run["command"], run["outcome"], run["exit_code"]) == ("calculate", "calculated", 0)
    assert run["totals"]["printed"] is None
    assert run["explanation"] is None


def test_unknown_command_is_refused(client: TestClient) -> None:
    response = post_run(client, example("matching.json"), "adjust")
    assert response.status_code == 422
    assert client.get("/api/runs").json() == {"runs": []}


def test_history_detail_report_source_and_verify(client: TestClient) -> None:
    first = post_run(client, example("differing.json")).json()["run"]["run_id"]
    again = post_run(client, example("differing.json")).json()
    assert again["document_was_new"] is False
    post_run(client, example("missing-data.json"), "calculate")

    runs = client.get("/api/runs").json()["runs"]
    assert [r["run_id"] for r in runs] == [3, 2, 1]
    assert [r["run_id"] for r in client.get("/api/runs", params={"limit": 1}).json()["runs"]] == [3]
    assert no_json_numbers(runs)

    detail = client.get(f"/api/runs/{first}").json()
    assert detail["run"]["run_id"] == first
    assert detail["report"] == cli_json("differing.json", "reconcile")
    assert len(detail["report_sha256"]) == 64

    report = client.get(f"/api/runs/{first}/report")
    assert report.headers["content-type"] == "application/json"
    assert report.content.decode("utf-8") == json_report.dumps(detail["report"])

    source = client.get(f"/api/runs/{first}/source")
    assert source.content == example("differing.json")

    verify = client.post(f"/api/runs/{first}/verify").json()
    assert verify["matches"] is True
    assert verify["stored_sha256"] == verify["recomputed_sha256"] == detail["report_sha256"]


def test_verify_reports_a_difference_without_writing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = post_run(client, example("differing.json")).json()["run"]["run_id"]
    real = json_report.dumps
    monkeypatch.setattr(json_report, "dumps", lambda doc: real(doc) + " ")
    verify = client.post(f"/api/runs/{run_id}/verify").json()
    assert verify["matches"] is False
    assert "unchanged" in verify["message"]
    monkeypatch.undo()
    assert client.post(f"/api/runs/{run_id}/verify").json()["matches"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/runs/99"),
        ("get", "/api/runs/99/report"),
        ("get", "/api/runs/99/source"),
        ("post", "/api/runs/99/verify"),
    ],
)
def test_unknown_run_is_404(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path)
    assert response.status_code == 404
    assert response.json()["error"] == "run-not-found"


def test_bad_limit_is_422(client: TestClient) -> None:
    assert client.get("/api/runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/runs", params={"limit": 501}).status_code == 422


@pytest.mark.parametrize("bill_id", ["GB1", "GB2", "GB3"])
def test_golden_bills_through_the_api(client: TestClient, bill_id: str) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("golden_api", GOLDEN / "test_golden.py")
    assert spec is not None
    assert spec.loader is not None
    golden = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(golden)
    signed = golden.signed(bill_id)
    calc, recon = signed["calculation"], signed["reconciliation"]
    data = golden.input_json(bill_id)
    data["printed"] = golden.printed_variant(bill_id, calc)
    run = post_run(client, json.dumps(data).encode("utf-8")).json()["run"]

    def paise(node: dict[str, str] | None) -> str:
        return golden.MISSING if node is None else node["paise"]

    assert paise(run["totals"]["calculated"]) == calc["total_paise"]
    assert paise(run["totals"]["printed"]) == recon["printed_total_paise"]
    want_difference = recon["total_difference_paise"]
    got_difference = run["totals"]["difference"]
    if want_difference == golden.UNDETERMINED:
        assert got_difference is None
    else:
        assert got_difference["paise"] == want_difference
    assert run["explanation"] == recon["explanation"].lower()
    assert str(run["exit_code"]) == recon["exit_code"]


# ---- database failures -------------------------------------------------------


def unreachable_engine() -> Engine:
    return create_engine("postgresql+psycopg://samay:x@127.0.0.1:1/samay?connect_timeout=2")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/health"),
        ("post", "/api/runs"),
        ("get", "/api/runs"),
        ("get", "/api/runs/1"),
        ("post", "/api/runs/1/verify"),
    ],
)
def test_database_down_is_503(method: str, path: str) -> None:
    engine = unreachable_engine()
    with TestClient(create_app(engine), raise_server_exceptions=False) as test_client:
        response = test_client.request(method, path, content=example("matching.json"))
    engine.dispose()
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "database-unavailable"
    assert "make db-up" in body["message"]
    assert ":x@" not in response.text


def test_validate_works_without_a_database() -> None:
    engine = unreachable_engine()
    with TestClient(create_app(engine), raise_server_exceptions=False) as test_client:
        response = test_client.post("/api/validate", content=example("matching.json"))
    engine.dispose()
    assert response.status_code == 200


def test_database_not_configured_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAMAY_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAMAY_DB_PASSWORD", raising=False)
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/runs")
    assert response.status_code == 503
    assert response.json()["error"] == "database-not-configured"


def test_engine_is_created_from_settings_and_disposed(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAMAY_DATABASE_URL", db.url.render_as_string(hide_password=False))
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        assert test_client.get("/api/health").status_code == 200
        assert test_client.get("/api/health").status_code == 200


def test_internal_error_is_500_without_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(api_module, "list_runs", broken)
    response = client.get("/api/runs")
    assert response.status_code == 500
    assert response.json() == {
        "error": "internal-error",
        "message": "SAMAY internal error: RuntimeError",
    }


def test_module_level_app_starts_without_a_database() -> None:
    assert api_module.app.title == "SAMAY API"
    assert any(getattr(r, "path", None) == "/api/runs" for r in api_module.app.routes)
