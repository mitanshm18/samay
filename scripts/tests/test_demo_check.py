"""scripts/demo_check.py against a small fake API (standard library only)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "demo_check.py"
_spec = importlib.util.spec_from_file_location("demo_check", SCRIPT)
assert _spec is not None and _spec.loader is not None
demo_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo_check)


def money(paise: str | None) -> dict[str, Any]:
    if paise is None:
        return {"value": None, "provenance": "missing"}
    return {"value": "x", "paise": paise}


class FakeApi(BaseHTTPRequestHandler):
    """Answers like the SAMAY API for one saved run. Class attributes set the faults."""

    total: str | None = "100"
    summary_total: dict[str, str] | None = {"paise": "100", "inr": "₹1.00"}
    verify_matches = True
    saving_status = "illustrative"
    saved: bytes = b""

    def log_message(self, *args: object) -> None:
        pass

    def send(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def report(self) -> dict[str, Any]:
        return {
            "calculation": {"total": money(self.total)},
            "reconciliation": {
                "total": {"printed": money("100"), "difference": money("0" if self.total else None)},
                "lines": [],
            },
        }

    def run(self) -> dict[str, Any]:
        cls = type(self)
        difference = {"paise": "0", "inr": "₹0.00"} if cls.summary_total else None
        return {
            "run_id": 1,
            "outcome": "clean",
            "exit_code": 0,
            "synthetic": True,
            "totals": {
                "calculated": cls.summary_total,
                "printed": {"paise": "100", "inr": "₹1.00"},
                "difference": difference,
            },
        }

    def optimisation(self) -> dict[str, Any]:
        cls = type(self)
        amount = {"paise": "10", "inr": "₹0.10"} if cls.summary_total else None
        return {
            "synthetic": True,
            "current_total": cls.summary_total,
            "recommendations": [{"key": "k", "saving": {"status": cls.saving_status, "amount": amount}}],
        }

    def do_GET(self) -> None:
        if self.path == "/":
            self.send(200, b"<html><title>SAMAY</title></html>", "text/html")
        elif self.path == "/api/health":
            self.send(200, b'{"status": "ok", "database": "ok"}')
        elif self.path == "/api/runs/1":
            self.send(200, json.dumps({"run": self.run(), "report": self.report()}).encode())
        elif self.path == "/api/runs/1/report":
            self.send(200, json.dumps(self.report()).encode())
        elif self.path == "/api/runs/1/optimisation":
            self.send(200, json.dumps(self.optimisation()).encode())
        elif self.path == "/api/runs/1/source":
            self.send(200, type(self).saved)
        else:
            self.send(404, b"{}")

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("content-length", "0")))
        if self.path == "/api/validate":
            self.send(200, b'{"valid": true}')
        elif self.path == "/api/runs?command=reconcile":
            type(self).saved = body
            self.send(201, json.dumps({"run": self.run(), "report": self.report()}).encode())
        elif self.path == "/api/runs/1/verify":
            self.send(200, json.dumps({"matches": type(self).verify_matches}).encode())
        else:
            self.send(404, b"{}")


class DemoCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeApi.total = "100"
        FakeApi.summary_total = {"paise": "100", "inr": "₹1.00"}
        FakeApi.verify_matches = True
        FakeApi.saving_status = "illustrative"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / "bill.json").write_bytes(b'{"format": "samay.bill/1"}')
        self.original_bills = demo_check.BILLS
        demo_check.BILLS = Path(folder.name)

    def tearDown(self) -> None:
        demo_check.BILLS = self.original_bills
        self.server.shutdown()
        self.server.server_close()

    def run_check(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demo_check.main(["--api", self.url, "--web", self.url, *args])
        return code, out.getvalue()

    def test_passes_when_everything_agrees(self) -> None:
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("ok   bill.json: run #1, clean, total payable ₹1.00", out)

    def test_fails_when_verify_does_not_match(self) -> None:
        FakeApi.verify_matches = False
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("FAIL bill.json: verify", out)

    def test_fails_when_a_missing_total_is_shown_as_an_amount(self) -> None:
        FakeApi.total = None  # the report says MISSING, the summary shows ₹1.00
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("FAIL bill.json: run summary total differs", out)

    def test_accepts_a_missing_total_shown_as_missing(self) -> None:
        FakeApi.total = None
        FakeApi.summary_total = None
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("total payable MISSING", out)

    def test_fails_when_a_synthetic_saving_is_called_an_estimate(self) -> None:
        FakeApi.saving_status = "estimated"
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("FAIL bill.json: optimisation: k presents a synthetic-tariff saving", out)

    def test_explains_when_the_api_is_not_running(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demo_check.main(["--api", "http://127.0.0.1:9", "--web", ""])
        self.assertEqual(code, 1)
        self.assertIn("make api", out.getvalue())


if __name__ == "__main__":
    unittest.main()
