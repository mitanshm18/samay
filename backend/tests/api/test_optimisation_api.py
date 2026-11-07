"""The optimisation endpoints: worked out from the exact saved bill, nothing saved."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from dbhelpers import example
from samay.api import create_app
from samay.io import load_bill
from samay.optimise import optimisation_document, optimise


@pytest.fixture
def client(db: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(db), raise_server_exceptions=False) as test_client:
        yield test_client


def no_numbers(value: object) -> bool:
    if isinstance(value, dict):
        return all(no_numbers(v) for k, v in value.items() if k != "run_id")
    if isinstance(value, list):
        return all(no_numbers(v) for v in value)
    return isinstance(value, str | bool) or value is None


def test_saved_run_optimisation_is_the_engine_document(client: TestClient) -> None:
    data = example("golden-gb2.json")
    run_id = client.post("/api/runs", content=data).json()["run"]["run_id"]
    runs_before = client.get("/api/runs").json()
    response = client.get(f"/api/runs/{run_id}/optimisation")
    assert response.status_code == 200
    body = response.json()
    loaded = load_bill(data)
    assert body == {"run_id": run_id, **optimisation_document(optimise(loaded.bill, loaded.tariff))}
    assert no_numbers(body)
    excess = next(r for r in body["recommendations"] if r["key"] == "excess-demand")
    assert excess["kind"] == "actionable"
    assert excess["saving"]["status"] == "illustrative"
    assert excess["saving"]["amount"] == {"paise": "3898100", "inr": "₹38,981.00"}
    assert client.get("/api/runs").json() == runs_before  # nothing saved


def test_missing_total_gives_insufficient_data(client: TestClient) -> None:
    run_id = client.post("/api/runs", content=example("golden-gb3.json")).json()["run"]["run_id"]
    body = client.get(f"/api/runs/{run_id}/optimisation").json()
    assert body["current_total"] is None
    assert all(r["saving"]["amount"] is None for r in body["recommendations"])


def test_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/api/runs/999/optimisation").status_code == 404


def test_posted_bill_needs_no_database() -> None:
    engine = create_engine("postgresql+psycopg://samay:x@127.0.0.1:1/samay?connect_timeout=2")
    with TestClient(create_app(engine), raise_server_exceptions=False) as test_client:
        ok = test_client.post("/api/optimise", content=example("matching.json"))
        bad = test_client.post("/api/optimise", content=b"{}")
        down = test_client.get("/api/runs/1/optimisation")
    engine.dispose()
    assert ok.status_code == 200
    assert ok.json()["format"] == "samay.optimisation/1"
    assert bad.status_code == 422
    assert bad.json()["errors"]
    assert down.status_code == 503
