"""Static guards for scripts/db.sh (standard library only, no Docker needed).

db.sh may only address SAMAY's own Compose project, and must never delete data,
download images or clean up anything else on the machine.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "db.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")
CODE = "\n".join(line.split("#", 1)[0] for line in TEXT.splitlines())  # comments removed


class DbScriptTests(unittest.TestCase):
    def test_no_destructive_or_global_docker_commands(self) -> None:
        forbidden = [
            r"\bprune\b",
            r"\bdown\s+(-v|--volumes)\b",
            r"\bdocker\s+(rm|rmi|kill|stop|pull|system|volume\s+rm|network\s+rm)\b",
            r"\bcompose\s+(pull|rm|kill)\b",
            r"\b(build|--build)\b",
        ]
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, CODE), pattern)

    def test_every_compose_call_uses_this_folders_compose_file(self) -> None:
        calls = re.findall(r"docker compose[^\n]*", CODE)
        self.assertEqual(len(calls), 1, calls)  # only inside the compose() helper
        self.assertIn('-f "$ROOT/compose.yaml"', calls[0])

    def test_up_runs_every_check_before_starting(self) -> None:
        up = CODE.split("  up)", 1)[1].split(";;", 1)[0]
        order = [up.index(step) for step in
                 ("scope_check", "disk_check", "image_check", "owner_check", "compose up")]
        self.assertEqual(order, sorted(order))
        self.assertIn("MIN_FREE_GB=20", CODE)

    def test_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_usage_without_env_file_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Run a copy from a folder with no .env and no compose.yaml.
            (Path(tmp) / "scripts").mkdir()
            copy = Path(tmp) / "scripts" / "db.sh"
            copy.write_text(TEXT, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(copy), "up"], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(".env not found", result.stderr)
            result = subprocess.run(
                ["bash", str(copy), "unknown"], capture_output=True, text=True, check=False
            )
            self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()
