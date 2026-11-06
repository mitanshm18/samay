"""SAMAY command line: python -m samay.cli validate|calculate|reconcile BILL.json

Exit codes (decision 0004, D7):
  0  validate/calculate: valid; reconcile: everything compared and equal
  1  reconcile: any difference, line not compared, or total not determinable
  2  invalid input (all problems listed), or a usage error
  3  internal error (a SAMAY bug); no traceback unless --debug

Output goes to stdout only (D9). With --format json, stdout holds one JSON
document and nothing else; warnings and errors are inside it.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import TextIO

from samay.billing import ReconciliationReport, recompute_bill, reconcile
from samay.tariffs import Tariff

from .io import json_report, text_report
from .io.errors import BillInputError, InputError
from .io.json_bill import MAX_BYTES, LoadedBill, load_bill

EXIT_OK = 0
EXIT_DIFFERENCES = 1
EXIT_INVALID = 2
EXIT_INTERNAL = 3


def reconcile_exit_code(report: ReconciliationReport) -> int:
    """0 only when every recalculated line was compared and matches and totals agree."""
    return EXIT_OK if report.is_clean else EXIT_DIFFERENCES


def _read(path: str) -> bytes:
    """The file's bytes, or BillInputError for anything that stops it being read."""
    file = Path(path)
    try:
        with file.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise BillInputError((InputError("$", "cannot-read-file", f"{path}: {reason}"),)) from None
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m samay.cli",
        description="Validate, calculate and reconcile electricity bills (samay.bill/1 JSON).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("validate", "check a bill file and list every problem"),
        ("calculate", "recalculate the bill"),
        ("reconcile", "recalculate and compare with the printed bill"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("bill", help="path to a samay.bill/1 JSON file")
        command.add_argument("--format", choices=("text", "json"), default="text")
        command.add_argument(
            "--debug", action="store_true", help="show a traceback on an internal error"
        )
    return parser


def _run(command: str, loaded: LoadedBill, as_json: bool, out: TextIO) -> int:
    bill, tariff = loaded.bill, loaded.tariff
    if command == "validate":
        if as_json:
            out.write(
                json_report.dumps(
                    json_report.validation_document(
                        command,
                        EXIT_OK,
                        warnings=loaded.warnings,
                        tariff=(tariff.tariff_id, tariff.name, tariff.status, _banner(tariff)),
                    )
                )
            )
        else:
            out.write(text_report.validation_text(bill.bill_id, _banner(tariff), loaded.warnings))
        return EXIT_OK
    result = recompute_bill(bill, tariff)
    if command == "calculate":
        if as_json:
            out.write(json_report.dumps(json_report.calculation_document(result, EXIT_OK)))
        else:
            out.write(text_report.calculation_text(result))
        return EXIT_OK
    report = reconcile(bill, result)
    code = reconcile_exit_code(report)
    if as_json:
        out.write(json_report.dumps(json_report.reconciliation_document(report, code)))
    else:
        out.write(text_report.reconciliation_text(report))
    return code


def _banner(tariff: Tariff) -> str | None:
    """The same banner recompute_bill puts on a breakdown (checked by a test)."""
    if not tariff.is_synthetic:
        return None
    return (
        f"{tariff.tariff_id} is SYNTHETIC: its rates are made up and are not UP tariff rates. "
        "This is not a real bill."
    )


def main(
    argv: list[str] | None = None, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    args = _parser().parse_args(argv)  # usage errors: argparse prints usage, exits 2
    as_json = args.format == "json"
    try:
        loaded = load_bill(_read(args.bill))
        return _run(args.command, loaded, as_json, out)
    except BillInputError as error:
        if as_json:
            out.write(
                json_report.dumps(
                    json_report.validation_document(args.command, EXIT_INVALID, errors=error.errors)
                )
            )
        else:
            err.write(text_report.errors_text(error.errors))
        return EXIT_INVALID
    except Exception as error:  # a bug: never shown as an input error, never a raw traceback
        message = f"SAMAY internal error: {type(error).__name__}: {error} (please report)"
        if args.debug:
            traceback.print_exc(file=err)
        if as_json:
            out.write(json_report.dumps(json_report.internal_error_document(args.command, message)))
        else:
            err.write(message + "\n")
        return EXIT_INTERNAL


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    sys.exit(main())
