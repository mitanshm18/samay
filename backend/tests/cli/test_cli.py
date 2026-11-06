"""The command line: exit codes, clean stdout, no tracebacks, nothing written."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from samay import cli
from samay.billing import recompute_bill
from samay.io import load_bill
from samay.tariffs import get_tariff

BACKEND = Path(__file__).resolve().parents[2]
EXAMPLES = BACKEND.parent / "examples" / "bills"


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()


def bill(name: str) -> str:
    return str(EXAMPLES / f"{name}.json")


def write(tmp_path: Path, content: bytes) -> str:
    path = tmp_path / "bill.json"
    path.write_bytes(content)
    return str(path)


# ---- exit codes ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [("matching", 0), ("differing", 1), ("pass-through", 1), ("missing-data", 1)],
)
def test_reconcile_exit_codes(name: str, expected: int) -> None:
    for fmt in ("text", "json"):
        code, out, err = run("reconcile", bill(name), "--format", fmt)
        assert code == expected
        assert err == ""
        if fmt == "json":
            assert json.loads(out)["exit_code"] == str(expected)


@pytest.mark.parametrize("command", ["validate", "calculate"])
@pytest.mark.parametrize("name", ["matching", "differing", "pass-through", "missing-data"])
def test_validate_and_calculate_exit_zero_for_valid_files(command: str, name: str) -> None:
    code, out, err = run(command, bill(name))
    assert (code, err) == (0, "")
    assert out.startswith("*** SAMAY-DEMO-1 is SYNTHETIC")


def test_invalid_input_exits_2_and_lists_every_error(tmp_path: Path) -> None:
    data: dict[str, Any] = json.loads(Path(bill("matching")).read_text("utf-8"))
    data["readings"]["kwh"]["value"] = 41250
    data["extra"] = "x"
    path = write(tmp_path, json.dumps(data).encode())
    code, out, err = run("reconcile", path)
    assert (code, out) == (2, "")
    assert "2 problem(s)" in err
    assert "[number-not-string]" in err
    assert "[unknown-key]" in err
    code, out, err = run("reconcile", path, "--format", "json")
    assert (code, err) == (2, "")
    doc = json.loads(out)
    assert doc["valid"] is False
    assert doc["exit_code"] == "2"
    assert sorted(e["code"] for e in doc["errors"]) == ["number-not-string", "unknown-key"]


def test_unreadable_file(tmp_path: Path) -> None:
    code, out, err = run("validate", str(tmp_path / "absent.json"))
    assert (code, out) == (2, "")
    assert "[cannot-read-file]" in err
    code, _, err = run("validate", str(tmp_path))  # a directory
    assert code == 2
    assert "[cannot-read-file]" in err


def test_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (
        [],
        ["explain", bill("matching")],
        ["reconcile"],
        ["calculate", "x", "--format", "xml"],
    ):
        with pytest.raises(SystemExit) as stopped:
            cli.main(argv)
        assert stopped.value.code == 2
    assert capsys.readouterr().out == ""


def test_internal_error_exits_3_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> None:
        raise ZeroDivisionError("bug")

    monkeypatch.setattr(cli, "recompute_bill", broken)
    code, out, err = run("calculate", bill("matching"))
    assert (code, out) == (3, "")
    assert err == "SAMAY internal error: ZeroDivisionError: bug (please report)\n"
    code, out, err = run("calculate", bill("matching"), "--format", "json")
    assert (code, err) == (3, "")
    assert json.loads(out)["internal_error"].startswith("SAMAY internal error")
    code, out, err = run("calculate", bill("matching"), "--debug")
    assert code == 3
    assert err.startswith("Traceback")
    assert err.endswith("(please report)\n")


def test_reconcile_exit_code_follows_is_clean() -> None:
    assert (cli.EXIT_OK, cli.EXIT_DIFFERENCES, cli.EXIT_INVALID, cli.EXIT_INTERNAL) == (0, 1, 2, 3)


@pytest.mark.parametrize("name", ["GB1", "GB2", "GB3"])
def test_golden_inputs_validate(name: str) -> None:
    """Validation only: nothing is calculated on the golden inputs before sign-off."""
    path = BACKEND / "tests" / "golden" / "inputs" / f"{name}.json"
    code, out, err = run("validate", str(path), "--format", "json")
    assert (code, err) == (0, "")
    assert json.loads(out)["valid"] is True


# ---- output -------------------------------------------------------------------------


def test_validate_json() -> None:
    code, out, _ = run("validate", bill("pass-through"), "--format", "json")
    doc = json.loads(out)
    assert code == 0
    assert doc["valid"] is True
    assert doc["synthetic"] is True
    assert sorted({w["code"] for w in doc["warnings"]}) == ["input-estimated", "synthetic-tariff"]


def test_text_reports() -> None:
    _, out, _ = run("reconcile", bill("pass-through"))
    assert "CALCULATED_ONLY" in out or "calculated only" in out
    assert "taken as printed and not checked" in out
    assert "not determinable" in out
    _, out, _ = run("reconcile", bill("matching"))
    assert "Nothing was taken as printed." in out
    _, out, _ = run("calculate", bill("missing-data"))
    assert "MISSING" in out


def test_validate_banner_equals_breakdown_banner() -> None:
    tariff = get_tariff("SAMAY-DEMO-1")
    loaded = load_bill(Path(bill("matching")).read_bytes())
    assert cli._banner(tariff) == recompute_bill(loaded.bill, tariff).banner


def test_no_files_are_written(tmp_path: Path) -> None:
    path = write(tmp_path, Path(bill("matching")).read_bytes())
    before = sorted(tmp_path.iterdir())
    for command in ("validate", "calculate", "reconcile"):
        run(command, path, "--format", "json")
    assert sorted(tmp_path.iterdir()) == before


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
@given(st.binary(max_size=300))
def test_random_bytes_exit_2_with_clean_json(tmp_path: Path, data: bytes) -> None:
    path = write(tmp_path, data)
    code, out, err = run("reconcile", path, "--format", "json")
    assert (code, err) == (2, "")
    assert json.loads(out)["valid"] is False


# ---- as a real process --------------------------------------------------------------


def process(*argv: str) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONPATH": str(BACKEND / "src"), "PYTHONIOENCODING": "ascii"}
    return subprocess.run(
        [sys.executable, "-m", "samay.cli", *argv], capture_output=True, env=env, check=False
    )


@pytest.mark.parametrize(("name", "expected"), [("matching", 0), ("missing-data", 1)])
def test_process_json_stdout_is_only_json(name: str, expected: int) -> None:
    done = process("reconcile", bill(name), "--format", "json")
    assert done.returncode == expected
    assert done.stderr == b""
    doc = json.loads(done.stdout.decode("utf-8"))  # UTF-8 even with an ASCII terminal
    assert doc["exit_code"] == str(expected)


def test_process_text_uses_utf8() -> None:
    done = process("reconcile", bill("pass-through"))
    assert done.returncode == 1
    assert "₹" in done.stdout.decode("utf-8")
    assert b"Traceback" not in done.stdout + done.stderr


def test_process_usage_error() -> None:
    done = process("reconcile")
    assert done.returncode == 2
    assert done.stdout == b""
    assert b"usage:" in done.stderr
