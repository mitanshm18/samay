#!/usr/bin/env python3
"""Demo readiness check: every example bill through the running SAMAY app.

Standard library only. Needs `make api` (and, for the web check, `make web`) running.
For each bill in examples/bills it does what the web page does: validate, calculate,
reconcile and save, open the run, fetch the exact report and bill file, and verify.
It checks that the pieces agree, that a MISSING total is never shown as an amount,
and that the three hand-checked golden bills give the hand-checked totals.

Each run of this check SAVES one run per bill: they become the demo history.

    python3 scripts/demo_check.py [--api http://127.0.0.1:8000] [--web http://127.0.0.1:5173]
    python3 scripts/demo_check.py --web ""        # API only
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BILLS = ROOT / "examples" / "bills"
GOLDEN = ROOT / "backend" / "tests" / "golden" / "expected"
MISSING = "MISSING"
UNDETERMINED = "NOT DETERMINABLE"


class CheckFailed(Exception):
    pass


class Http:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        request = urllib.request.Request(self.base + path, data=body, method=method)
        if body is not None:
            request.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, OSError) as error:
            raise CheckFailed(f"cannot reach {self.base} ({error}).") from error

    def json(self, method: str, path: str, body: bytes | None = None, want: int = 200) -> Any:
        status, data = self.call(method, path, body)
        if status != want:
            raise CheckFailed(f"{method} {path}: HTTP {status}, expected {want}: {data[:300]!r}")
        return json.loads(data)


def paise(node: dict[str, Any] | None) -> str:
    """A report amount as the hand-check writes it."""
    return MISSING if node is None or node.get("value") is None else str(node["paise"])


def summary_paise(node: dict[str, str] | None, absent: str) -> str:
    return absent if node is None else node["paise"]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def check_bill(api: Http, path: Path) -> str:
    data = path.read_bytes()
    validation = api.json("POST", "/api/validate", data)
    check(validation["valid"] is True, "validate: bill is not valid")

    created = api.json("POST", "/api/runs?command=reconcile", data, want=201)
    run = created["run"]
    run_id = run["run_id"]
    detail = api.json("GET", f"/api/runs/{run_id}")
    report = detail["report"]
    check(report == created["report"], "the saved report differs from the one returned on save")
    status, raw = api.call("GET", f"/api/runs/{run_id}/report")
    check(status == 200 and json.loads(raw) == report, "report download differs from the run")
    status, source = api.call("GET", f"/api/runs/{run_id}/source")
    check(status == 200 and source == data, "bill file download is not the exact bill sent")
    verify = api.json("POST", f"/api/runs/{run_id}/verify")
    check(verify["matches"] is True, "verify: recalculation does not match the saved report")

    totals = detail["run"]["totals"]
    rec = report["reconciliation"]
    calculated = paise(report["calculation"]["total"])
    check(
        summary_paise(totals["calculated"], MISSING) == calculated,
        "run summary total differs from the report",
    )
    check(
        summary_paise(totals["printed"], MISSING) == paise(rec["total"]["printed"]),
        "run summary printed total differs from the report",
    )
    difference = rec["total"]["difference"]
    check(
        summary_paise(totals["difference"], UNDETERMINED)
        == (UNDETERMINED if difference is None or difference.get("value") is None
            else difference["paise"]),
        "run summary difference differs from the report",
    )
    if calculated == MISSING:
        check(totals["calculated"] is None, "a MISSING total is shown as an amount")
        check(totals["difference"] is None, "a difference from a MISSING total is shown")
    check(run["synthetic"] is True, "synthetic tariff status was lost")

    if path.stem.startswith("golden-"):
        golden_file = GOLDEN / f"{path.stem.removeprefix('golden-').upper()}.json"
        want = json.loads(golden_file.read_text("utf-8"))["reconciliation"]
        got = {
            "printed_total_paise": summary_paise(totals["printed"], MISSING),
            "calculated_total_paise": summary_paise(totals["calculated"], MISSING),
            "total_difference_paise": summary_paise(totals["difference"], UNDETERMINED),
            "exit_code": str(run["exit_code"]),
        }
        check(got == {k: want[k] for k in got}, f"differs from the hand-check: {got} vs {want}")
        lines = {line["code"]: line["status"] for line in rec["lines"]}
        check(
            lines == {code: item["status"] for code, item in want["lines"].items()},
            "line statuses differ from the hand-check",
        )

    total = totals["calculated"]["inr"] if totals["calculated"] else "MISSING"
    return f"run #{run_id}, {run['outcome']}, total payable {total}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--web", default="http://127.0.0.1:5173")
    args = parser.parse_args(argv)
    api = Http(args.api)
    failures = 0
    try:
        health = api.json("GET", "/api/health")
        print(f"ok   API {args.api} (database {health['database']})")
        if args.web:
            web = Http(args.web)
            status, page = web.call("GET", "/")
            check(status == 200 and b"<title>SAMAY" in page, f"web page not served at {args.web}")
            check(web.json("GET", "/api/health")["status"] == "ok", "web page cannot reach the API")
            print(f"ok   web page {args.web} (and its link to the API)")
    except CheckFailed as error:
        print(f"FAIL {error}\n     Start the database, API and web page: make db-up, make api, make web")
        return 1
    for path in sorted(BILLS.glob("*.json")):
        try:
            print(f"ok   {path.name}: {check_bill(api, path)}")
        except CheckFailed as error:
            failures += 1
            print(f"FAIL {path.name}: {error}")
    if failures:
        print(f"\n{failures} bill(s) failed.")
        return 1
    print("\nDemo check passed. The runs above are now in the bill history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
