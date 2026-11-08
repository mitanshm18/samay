"""Python version check in scripts/doctor.sh (standard library only, no Docker needed).

The doctor must reject any python3 older than the backend's requires-python
(3.13) and accept 3.13 or newer. A fake python3 on PATH reports a chosen version
for the doctor's version query and hands every other call to the real Python.
On CI (--ci) an old python3 is a WARN, because the CI "checks" job runs only
standard-library helper scripts with the runner's own python3.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts" / "doctor.sh"
PYPROJECT = ROOT / "backend" / "pyproject.toml"

FAKE_PYTHON = """#!/bin/sh
case "$*" in
  *sys.version_info*) echo "{version}" ;;
  *) exec "{real}" "$@" ;;
esac
"""


def run_doctor_with_python(version: str, *, ci: bool = False) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "python3"
        fake.write_text(FAKE_PYTHON.format(version=version, real=sys.executable), encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        env = dict(os.environ, PATH=f"{tmp}{os.pathsep}{os.environ.get('PATH', '')}")
        result = subprocess.run(
            ["bash", str(DOCTOR), *(["--ci"] if ci else [])],
            capture_output=True, text=True, env=env, check=False, timeout=120,
        )
        return result.stdout


class DoctorPythonVersionTests(unittest.TestCase):
    def test_minimum_matches_pyproject(self) -> None:
        required = re.search(r'requires-python\s*=\s*">=([0-9.]+)"',
                             PYPROJECT.read_text(encoding="utf-8"))
        minimum = re.search(r'^MIN_PYTHON="([0-9.]+)"', DOCTOR.read_text(encoding="utf-8"),
                            re.MULTILINE)
        if required is None or minimum is None:
            self.fail("requires-python or MIN_PYTHON not found")
        self.assertEqual(minimum.group(1), required.group(1))

    def test_python_3_12_is_rejected(self) -> None:
        out = run_doctor_with_python("3.12.9")
        self.assertIn("[FAIL] python3 3.12.9 is older than 3.13", out)
        self.assertNotIn("[ OK ] python3 3.12.9", out)

    def test_python_3_12_is_a_warning_in_ci_mode(self) -> None:
        out = run_doctor_with_python("3.12.9", ci=True)
        self.assertIn("[WARN] python3 3.12.9 is older than 3.13", out)
        self.assertNotIn("[ OK ] python3 3.12.9", out)

    def test_python_3_13_is_accepted(self) -> None:
        for version in ("3.13.0", "3.13.9", "3.14.1"):
            with self.subTest(version=version):
                out = run_doctor_with_python(version)
                self.assertIn(f"[ OK ] python3 {version}", out)
                self.assertNotIn(f"[FAIL] python3 {version}", out)


if __name__ == "__main__":
    unittest.main()
