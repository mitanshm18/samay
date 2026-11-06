"""Saved bills: python -m samay.db save|list|show|verify

  save FILE [--calculate-only]  check a samay.bill/1 file and save input + report
  list [--limit N]              saved runs, newest first
  show RUN_ID [--source]        the saved report exactly as produced (or the input)
  verify RUN_ID                 recalculate from the saved input; compare reports

Exit codes: 0 ok (save: everything matched), 1 save: differences found /
verify: report differs, 2 invalid bill, bad settings or unknown run,
3 database unreachable or internal error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError

from samay.cli import _read
from samay.core import Money
from samay.io import text_report
from samay.io.errors import BillInputError

from .config import DatabaseConfigError, database_url
from .store import RunNotFoundError, RunSummary, get_run, list_runs, save_bill, verify_run


def _rupees(paise: int | None, missing: str) -> str:
    return missing if paise is None else Money.from_paise(paise).format_inr()


def _summary_line(run: RunSummary) -> str:
    total = _rupees(run.calculated_total_paise, "MISSING")
    text = f"#{run.run_id}  {run.bill_id}  {run.command}  exit {run.exit_code}  total {total}"
    if run.command == "reconcile":
        printed = _rupees(run.printed_total_paise, "not given or MISSING")
        diff = _rupees(run.total_difference_paise, "not determinable")
        text += f"  printed {printed}  difference {diff}  explanation {run.explanation}"
    tag = "SYNTHETIC" if run.tariff_status == "synthetic" else "verified"
    return f"{text}  [{run.tariff_id}, {tag}]"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m samay.db", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="action", required=True)
    save = commands.add_parser("save", help="check a bill file and save input + report")
    save.add_argument("bill")
    save.add_argument("--calculate-only", action="store_true", help="recalculate, no comparison")
    listing = commands.add_parser("list", help="saved runs, newest first")
    listing.add_argument("--limit", type=_positive, default=50)
    show = commands.add_parser("show", help="print a saved report exactly as produced")
    show.add_argument("run_id", type=int)
    show.add_argument("--source", action="store_true", help="print the saved input instead")
    verify = commands.add_parser("verify", help="recalculate a saved run and compare")
    verify.add_argument("run_id", type=int)
    return parser


def main(
    argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    args = _parser().parse_args(argv)
    try:
        engine = create_engine(database_url())
    except DatabaseConfigError as error:
        err.write(f"{error}\n")
        return 2
    try:
        return _act(args, engine, out)
    except BillInputError as error:
        err.write(text_report.errors_text(error.errors))
        return 2
    except RunNotFoundError as error:
        err.write(f"{error}\n")
        return 2
    except OperationalError:
        err.write("Cannot reach SAMAY's database. Start it with: make db-up\n")
        return 3
    except Exception as error:  # a bug: never shown as an input error
        err.write(f"SAMAY internal error: {type(error).__name__}: {error} (please report)\n")
        return 3
    finally:
        engine.dispose()


def _act(args: argparse.Namespace, engine: Engine, out: TextIO) -> int:
    if args.action == "save":
        command = "calculate" if args.calculate_only else "reconcile"
        saved = save_bill(engine, _read(args.bill), command)
        stored = get_run(engine, saved.run_id)
        banner = json.loads(stored.report_text)["banner"]
        if banner:
            out.write(banner + "\n")
        note = "new bill file" if saved.document_was_new else "bill file already saved"
        out.write(f"Saved ({note}): {_summary_line(stored.summary)}\n")
        out.write(f"Result: {stored.summary.outcome}. {stored.summary.outcome_text}\n")
        return saved.exit_code
    if args.action == "list":
        runs = list_runs(engine, args.limit)
        if not runs:
            out.write("No saved runs yet.\n")
        for run in runs:
            out.write(_summary_line(run) + "\n")
        return 0
    if args.action == "show":
        stored = get_run(engine, args.run_id)
        if args.source:
            out.write(stored.source_bytes.decode("utf-8"))
        else:
            out.write(stored.report_text)
        return 0
    result = verify_run(engine, args.run_id)
    if result.matches:
        out.write(f"Run #{result.run_id}: recalculated report is identical.\n")
        return 0
    out.write(
        f"Run #{result.run_id}: recalculated report DIFFERS from the saved one "
        f"(saved {result.stored_sha256[:12]}, now {result.recomputed_sha256[:12]}). "
        "The saved run is unchanged.\n"
    )
    return 1


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    sys.exit(main())
