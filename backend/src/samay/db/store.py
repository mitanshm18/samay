"""Save a bill with its report, and read saved runs back (decision 0005).

save_bill runs the same engine path as `python -m samay.cli` (load_bill ->
recompute_bill -> reconcile -> samay.report/1 JSON) and stores the exact input
bytes and the exact report text in one transaction. Nothing is calculated here:
the paise columns are copied from the engine's own results and checked against
the report text before anything is written.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from samay import __version__
from samay.billing import BillBreakdown, recompute_bill, reconcile
from samay.cli import reconcile_exit_code
from samay.core import Money, Traced
from samay.io import json_report
from samay.io.json_bill import FORMAT as BILL_FORMAT
from samay.io.json_bill import load_bill
from samay.io.json_report import FORMAT as REPORT_FORMAT

from .models import BillDocument, CalculationRun

ENGINE_VERSION = f"samay-backend {__version__}"
COMMANDS = ("calculate", "reconcile")


class RunNotFoundError(LookupError):
    """No saved run has this id."""


class ProjectionMismatchError(AssertionError):
    """The totals about to be saved do not match the report text: a SAMAY bug.

    Raised before anything is written, so the transaction saves nothing.
    """


@dataclass(frozen=True, slots=True)
class _Result:
    """What the engine produced for one command, before saving."""

    command: str
    bill_id: str
    exit_code: int
    report_text: str
    tariff_id: str
    tariff_name: str
    tariff_status: str
    calculated_total_paise: int | None
    printed_total_paise: int | None
    total_difference_paise: int | None
    explanation: str | None


@dataclass(frozen=True, slots=True)
class SavedRun:
    run_id: int
    bill_document_id: int
    bill_id: str
    command: str
    exit_code: int
    document_was_new: bool


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: int
    bill_id: str
    command: str
    exit_code: int
    tariff_id: str
    tariff_status: str
    calculated_total_paise: int | None
    printed_total_paise: int | None
    total_difference_paise: int | None
    explanation: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredRun:
    summary: RunSummary
    engine_version: str
    source_bytes: bytes
    source_sha256: str
    report_text: str
    report_sha256: str


@dataclass(frozen=True, slots=True)
class VerifyResult:
    run_id: int
    matches: bool
    stored_sha256: str
    recomputed_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _paise(value: Traced[Money] | None) -> int | None:
    """Known money as int paise; MISSING (or not given) as None, never 0."""
    if value is None or value.is_missing:
        return None
    money = value.raw
    if not isinstance(money, Money):
        raise TypeError(f"expected Money, got {type(money).__name__}")
    return money.paise


def _report_paise(node: dict[str, Any] | None) -> int | None:
    """The paise in a rendered traced value; None when it is MISSING or absent."""
    if node is None or node["value"] is None:
        return None
    return int(node["paise"])


def _calculate(data: bytes, command: str) -> _Result:
    """Run the engine exactly as the command line does. Invalid input raises
    BillInputError (or BillValidationError) before anything is saved."""
    if command not in COMMANDS:
        raise ValueError(f"command must be one of {COMMANDS}, got {command!r}")
    loaded = load_bill(data)
    breakdown: BillBreakdown = recompute_bill(loaded.bill, loaded.tariff)
    if command == "calculate":
        document = json_report.calculation_document(breakdown, 0)
        result = _Result(
            command=command,
            bill_id=loaded.bill.bill_id,
            exit_code=0,
            report_text=json_report.dumps(document),
            tariff_id=breakdown.tariff_id,
            tariff_name=breakdown.tariff_name,
            tariff_status=breakdown.tariff_status.value,
            calculated_total_paise=_paise(breakdown.total),
            printed_total_paise=None,
            total_difference_paise=None,
            explanation=None,
        )
    else:
        report = reconcile(loaded.bill, breakdown)
        code = reconcile_exit_code(report)
        document = json_report.reconciliation_document(report, code)
        result = _Result(
            command=command,
            bill_id=loaded.bill.bill_id,
            exit_code=code,
            report_text=json_report.dumps(document),
            tariff_id=report.tariff_id,
            tariff_name=report.tariff_name,
            tariff_status=report.tariff_status.value,
            calculated_total_paise=_paise(report.total.calculated),
            printed_total_paise=_paise(report.total.printed),
            total_difference_paise=_paise(report.total.difference),
            explanation=report.explanation.state.value,
        )
    _check_projection(result)
    return result


def _check_projection(result: _Result) -> None:
    """The columns must say exactly what the report text says."""
    doc = json.loads(result.report_text)
    expected: dict[str, object] = {
        "format": REPORT_FORMAT,
        "command": result.command,
        "exit_code": str(result.exit_code),
        "tariff_id": result.tariff_id,
        "tariff_name": result.tariff_name,
        "tariff_status": result.tariff_status,
        "calculated_total_paise": result.calculated_total_paise,
    }
    found: dict[str, object] = {
        "format": doc["format"],
        "command": doc["command"],
        "exit_code": doc["exit_code"],
        "tariff_id": doc["tariff"]["id"],
        "tariff_name": doc["tariff"]["name"],
        "tariff_status": doc["tariff"]["status"],
        "calculated_total_paise": _report_paise(doc["calculation"]["total"]),
    }
    if result.command == "reconcile":
        total = doc["reconciliation"]["total"]
        expected |= {
            "reconciled_calculated_paise": result.calculated_total_paise,
            "printed_total_paise": result.printed_total_paise,
            "total_difference_paise": result.total_difference_paise,
            "explanation": result.explanation,
        }
        found |= {
            "reconciled_calculated_paise": _report_paise(total["calculated"]),
            "printed_total_paise": _report_paise(total.get("printed")),
            "total_difference_paise": _report_paise(total["difference"]),
            "explanation": doc["reconciliation"]["explanation"]["state"].lower(),
        }
    if expected != found:
        raise ProjectionMismatchError(
            f"saved columns would differ from the report: {expected!r} != {found!r}"
        )


def save_bill(engine: Engine, data: bytes, command: str = "reconcile") -> SavedRun:
    """Validate and calculate the bill, then save the input and report atomically.

    An invalid bill raises (BillInputError) and nothing is written. The same file
    saved twice is stored once; each save adds a new run.
    """
    result = _calculate(data, command)
    digest = _sha256(data)
    with Session(engine) as session, session.begin():
        inserted = session.execute(
            insert(BillDocument)
            .values(
                bill_id=result.bill_id,
                tariff_id=result.tariff_id,
                format=BILL_FORMAT,
                source_bytes=data,
                source_sha256=digest,
            )
            .on_conflict_do_nothing(index_elements=["source_sha256"])
            .returning(BillDocument.id)
        ).scalar_one_or_none()
        document_id = (
            inserted
            if inserted is not None
            else session.execute(
                select(BillDocument.id).where(BillDocument.source_sha256 == digest)
            ).scalar_one()
        )
        run = CalculationRun(
            bill_document_id=document_id,
            command=result.command,
            engine_version=ENGINE_VERSION,
            tariff_id=result.tariff_id,
            tariff_name=result.tariff_name,
            tariff_status=result.tariff_status,
            exit_code=result.exit_code,
            report_format=REPORT_FORMAT,
            report_text=result.report_text,
            report_sha256=_sha256(result.report_text.encode("utf-8")),
            calculated_total_paise=result.calculated_total_paise,
            printed_total_paise=result.printed_total_paise,
            total_difference_paise=result.total_difference_paise,
            explanation=result.explanation,
        )
        session.add(run)
        session.flush()
        return SavedRun(
            run_id=run.id,
            bill_document_id=document_id,
            bill_id=result.bill_id,
            command=result.command,
            exit_code=result.exit_code,
            document_was_new=inserted is not None,
        )


def _summary(run: CalculationRun, bill_id: str) -> RunSummary:
    return RunSummary(
        run_id=run.id,
        bill_id=bill_id,
        command=run.command,
        exit_code=run.exit_code,
        tariff_id=run.tariff_id,
        tariff_status=run.tariff_status,
        calculated_total_paise=run.calculated_total_paise,
        printed_total_paise=run.printed_total_paise,
        total_difference_paise=run.total_difference_paise,
        explanation=run.explanation,
        created_at=run.created_at,
    )


def list_runs(engine: Engine, limit: int = 50) -> list[RunSummary]:
    """Newest first."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    with Session(engine) as session:
        rows = session.execute(
            select(CalculationRun, BillDocument.bill_id)
            .join(BillDocument, CalculationRun.bill_document_id == BillDocument.id)
            .order_by(CalculationRun.id.desc())
            .limit(limit)
        ).all()
        return [_summary(run, bill_id) for run, bill_id in rows]


def get_run(engine: Engine, run_id: int) -> StoredRun:
    with Session(engine) as session:
        row = session.execute(
            select(CalculationRun, BillDocument)
            .join(BillDocument, CalculationRun.bill_document_id == BillDocument.id)
            .where(CalculationRun.id == run_id)
        ).one_or_none()
        if row is None:
            raise RunNotFoundError(f"no saved run with id {run_id}")
        run, document = row
        return StoredRun(
            summary=_summary(run, document.bill_id),
            engine_version=run.engine_version,
            source_bytes=document.source_bytes,
            source_sha256=document.source_sha256,
            report_text=run.report_text,
            report_sha256=run.report_sha256,
        )


def verify_run(engine: Engine, run_id: int) -> VerifyResult:
    """Recalculate a saved bill from its stored bytes and compare the report text.

    Read-only: a difference is reported, never written back.
    """
    stored = get_run(engine, run_id)
    again = _calculate(stored.source_bytes, stored.summary.command)
    recomputed = _sha256(again.report_text.encode("utf-8"))
    return VerifyResult(
        run_id=run_id,
        matches=again.report_text == stored.report_text,
        stored_sha256=stored.report_sha256,
        recomputed_sha256=recomputed,
    )
