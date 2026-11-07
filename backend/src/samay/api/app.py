"""SAMAY HTTP API (decision 0006). Local only: served on 127.0.0.1.

Endpoints (all JSON):
  GET  /api/health                   API and database status
  POST /api/validate                 check a samay.bill/1 document, save nothing
  POST /api/runs?command=reconcile   check, calculate, reconcile and save (or command=calculate)
  GET  /api/runs?limit=50            saved runs, newest first
  GET  /api/runs/{id}                one saved run: summary and its report
  GET  /api/runs/{id}/report         the saved samay.report/1 text, byte for byte
  GET  /api/runs/{id}/source         the saved bill file, byte for byte
  POST /api/runs/{id}/verify         recalculate from the saved file and compare (writes nothing)

Money in summaries is a string of paise plus a formatted rupee string; a total
that is MISSING or not determinable is null (the report says why). Nothing
here calculates: every number comes from the engine via samay.db.
"""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from samay import __version__
from samay.cli import _banner
from samay.core import Money
from samay.db import (
    RunNotFoundError,
    RunSummary,
    get_run,
    list_runs,
    save_bill,
    verify_run,
)
from samay.db.config import DatabaseConfigError, database_url
from samay.io import json_report
from samay.io.errors import BillInputError
from samay.io.json_bill import MAX_BYTES, load_bill

DB_DOWN = "Cannot reach SAMAY's database. Start it with: make db-up"


class _Engines:
    """Creates the database engine on first use, so the app starts without one."""

    def __init__(self, engine: Engine | None) -> None:
        self._engine = engine
        self._owned = False
        self._lock = threading.Lock()

    def get(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = create_engine(database_url(), pool_pre_ping=True)
                self._owned = True
            return self._engine

    def close(self) -> None:
        with self._lock:
            if self._engine is not None and self._owned:
                self._engine.dispose()
                self._engine = None
                self._owned = False


def _money(paise: int | None) -> dict[str, str] | None:
    """Known money as strings (never a JSON number); None when MISSING."""
    if paise is None:
        return None
    return {"paise": str(paise), "inr": Money.from_paise(paise).format_inr()}


def summary(run: RunSummary) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "bill_id": run.bill_id,
        "command": run.command,
        "exit_code": run.exit_code,
        "outcome": run.outcome,
        "outcome_text": run.outcome_text,
        "tariff": {"id": run.tariff_id, "status": run.tariff_status},
        "synthetic": run.tariff_status == "synthetic",
        "totals": {
            "calculated": _money(run.calculated_total_paise),
            "printed": _money(run.printed_total_paise),
            "difference": _money(run.total_difference_paise),
        },
        "explanation": run.explanation,
        "created_at": run.created_at.isoformat(),
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


async def _body(request: Request) -> bytes:
    """The request body, read up to one byte past the bill size limit; load_bill
    then reports a too-large file as an input error, like the command line."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_BYTES:
            break
    return b"".join(chunks)[: MAX_BYTES + 1]


def create_app(engine: Engine | None = None) -> FastAPI:
    engines = _Engines(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engines.close()

    app = FastAPI(
        title="SAMAY API",
        version=__version__,
        description="Check, calculate, reconcile and save electricity bills (local only).",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(BillInputError)
    async def invalid_bill(request: Request, error: BillInputError) -> JSONResponse:
        command = request.query_params.get("command", "reconcile")
        if request.url.path == "/api/validate":
            command = "validate"
        document = json_report.validation_document(command, 2, errors=error.errors)
        return JSONResponse(status_code=422, content=document)

    @app.exception_handler(RunNotFoundError)
    async def not_found(_: Request, error: RunNotFoundError) -> JSONResponse:
        return _error(404, "run-not-found", str(error))

    @app.exception_handler(DatabaseConfigError)
    async def not_configured(_: Request, error: DatabaseConfigError) -> JSONResponse:
        return _error(503, "database-not-configured", str(error))

    @app.exception_handler(OperationalError)
    async def unreachable(_: Request, __: OperationalError) -> JSONResponse:
        return _error(503, "database-unavailable", DB_DOWN)

    @app.exception_handler(Exception)
    async def internal(_: Request, error: Exception) -> JSONResponse:
        # A SAMAY bug: never shown as an input error, never a traceback.
        return _error(500, "internal-error", f"SAMAY internal error: {type(error).__name__}")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        with engines.get().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__, "database": "ok"}

    @app.post("/api/validate")
    async def validate(request: Request) -> dict[str, Any]:
        loaded = load_bill(await _body(request))
        tariff = loaded.tariff
        return json_report.validation_document(
            "validate",
            0,
            warnings=loaded.warnings,
            tariff=(tariff.tariff_id, tariff.name, tariff.status, _banner(tariff)),
        )

    @app.post("/api/runs", status_code=201)
    async def create_run(
        request: Request, command: Literal["reconcile", "calculate"] = "reconcile"
    ) -> dict[str, Any]:
        data = await _body(request)
        engine = engines.get()
        saved = await run_in_threadpool(save_bill, engine, data, command)
        stored = await run_in_threadpool(get_run, engine, saved.run_id)
        return {
            "run": summary(stored.summary),
            "document_was_new": saved.document_was_new,
            "report": json.loads(stored.report_text),
        }

    @app.get("/api/runs")
    def runs(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        return {"runs": [summary(run) for run in list_runs(engines.get(), limit)]}

    @app.get("/api/runs/{run_id}")
    def run(run_id: int) -> dict[str, Any]:
        stored = get_run(engines.get(), run_id)
        return {
            "run": summary(stored.summary),
            "engine_version": stored.engine_version,
            "source_sha256": stored.source_sha256,
            "report_sha256": stored.report_sha256,
            "report": json.loads(stored.report_text),
        }

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: int) -> Response:
        stored = get_run(engines.get(), run_id)
        return Response(stored.report_text.encode("utf-8"), media_type="application/json")

    @app.get("/api/runs/{run_id}/source")
    def source(run_id: int) -> Response:
        stored = get_run(engines.get(), run_id)
        return Response(stored.source_bytes, media_type="application/json")

    @app.post("/api/runs/{run_id}/verify")
    def verify(run_id: int) -> dict[str, Any]:
        result = verify_run(engines.get(), run_id)
        return {
            "run_id": result.run_id,
            "matches": result.matches,
            "stored_sha256": result.stored_sha256,
            "recomputed_sha256": result.recomputed_sha256,
            "message": (
                "The recalculated report is identical to the saved one."
                if result.matches
                else "The recalculated report differs from the saved one. "
                "The saved run is unchanged."
            ),
        }

    return app


app = create_app()
