"""Tests for scripts/check_docker_scope.py (standard library only, no installs).

Run with:  python3 -m unittest discover -s scripts/tests -v
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_docker_scope.py"

_spec = importlib.util.spec_from_file_location("check_docker_scope", SCRIPT)
assert _spec and _spec.loader
scope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scope)

# Mirrors what `docker compose config --format json` produces for compose.yaml.
SAFE = {
    "name": "samay",
    "networks": {"default": {"name": "samay_default", "ipam": {}}},
    "services": {
        "db": {
            "container_name": "samay-db",
            "image": "postgres:16",
            "pull_policy": "never",
            "ports": [{"host_ip": "127.0.0.1", "target": 5432, "published": "55432", "protocol": "tcp"}],
            "volumes": [{"type": "volume", "source": "samay_pgdata", "target": "/var/lib/postgresql/data"}],
        }
    },
    "volumes": {"samay_pgdata": {"name": "samay_pgdata"}},
}


def variant(mutate):
    cfg = copy.deepcopy(SAFE)
    mutate(cfg)
    return cfg


class CheckDockerScopeTests(unittest.TestCase):
    def assert_rejected(self, cfg, fragment):
        problems = scope.check(cfg)
        self.assertTrue(problems, "expected the configuration to be rejected")
        self.assertTrue(any(fragment in p for p in problems), f"no problem mentions {fragment!r}: {problems}")

    def test_safe_config_passes(self):
        self.assertEqual(scope.check(SAFE), [])

    def test_wrong_project_name_rejected(self):
        self.assert_rejected(variant(lambda c: c.update(name="pratikriti")), "project name")

    def test_container_without_prefix_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].update(container_name="postgres")), "container_name")

    def test_missing_container_name_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].pop("container_name")), "container_name")

    def test_image_pull_allowed_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].update(pull_policy="missing")), "pull_policy")

    def test_local_build_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].update(build={"context": "."})), "building images")

    def test_port_on_all_interfaces_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"]["ports"][0].update(host_ip="0.0.0.0")), "127.0.0.1")

    def test_port_without_host_ip_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"]["ports"][0].pop("host_ip")), "127.0.0.1")

    def test_bind_mount_rejected(self):
        def m(c):
            c["services"]["db"]["volumes"][0] = {"type": "bind", "source": "/var/run/docker.sock", "target": "/sock"}

        self.assert_rejected(variant(m), "only named volumes")

    def test_foreign_volume_rejected(self):
        def m(c):
            c["services"]["db"]["volumes"][0]["source"] = "pratikriti_pgdata"
            c["volumes"] = {"pratikriti_pgdata": {"name": "pratikriti_pgdata"}}

        self.assert_rejected(variant(m), "must start with 'samay_'")

    def test_external_volume_rejected(self):
        self.assert_rejected(variant(lambda c: c["volumes"]["samay_pgdata"].update(external=True)), "external volumes")

    def test_external_network_rejected(self):
        self.assert_rejected(variant(lambda c: c["networks"]["default"].update(external=True)), "external networks")

    def test_foreign_network_name_rejected(self):
        self.assert_rejected(variant(lambda c: c["networks"]["default"].update(name="pratikriti_default")), "network 'default'")

    def test_host_network_mode_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].update(network_mode="host")), "network_mode")

    def test_privileged_rejected(self):
        self.assert_rejected(variant(lambda c: c["services"]["db"].update(privileged=True)), "privileged")

    def test_no_services_rejected(self):
        self.assert_rejected(variant(lambda c: c.update(services={})), "no services")


class CommandLineTests(unittest.TestCase):
    def run_script(self, cfg):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(cfg, fh)
            path = fh.name
        try:
            return subprocess.run([sys.executable, str(SCRIPT), path], capture_output=True, text=True, check=False)
        finally:
            Path(path).unlink()

    def test_exit_zero_for_safe_config(self):
        result = self.run_script(SAFE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_exit_one_for_unsafe_config(self):
        result = self.run_script(variant(lambda c: c.update(name="other")))
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)

    def test_exit_two_for_invalid_json(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
