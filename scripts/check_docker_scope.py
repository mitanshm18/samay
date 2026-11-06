#!/usr/bin/env python3
"""Refuse any Compose configuration that could touch non-SAMAY Docker resources.

Reads the output of `docker compose config --format json` (from a file path or
stdin) and checks it against the isolation rules in docs/docker-safety.md.
It only reads; it never calls Docker itself.

Usage:
    docker compose --env-file .env.example config --format json \\
        | python3 scripts/check_docker_scope.py
    python3 scripts/check_docker_scope.py rendered-config.json

Exit status: 0 if every rule passes, 1 if any rule fails, 2 on bad input.
"""

from __future__ import annotations

import json
import sys
from typing import Any

PROJECT = "samay"
CONTAINER_PREFIX = "samay-"
RESOURCE_PREFIX = "samay_"
ALLOWED_HOST_IPS = {"127.0.0.1"}
FORBIDDEN_SERVICE_KEYS = ("privileged", "pid", "ipc", "cap_add", "devices")


def check(config: dict[str, Any]) -> list[str]:
    """Return a list of rule violations; an empty list means the config is safe."""
    problems: list[str] = []

    if config.get("name") != PROJECT:
        problems.append(f"project name must be '{PROJECT}', found {config.get('name')!r}")

    services = config.get("services") or {}
    if not services:
        problems.append("no services defined")

    for svc_name, svc in services.items():
        where = f"service '{svc_name}'"

        container = svc.get("container_name")
        if not container or not str(container).startswith(CONTAINER_PREFIX):
            problems.append(f"{where}: container_name must start with '{CONTAINER_PREFIX}', found {container!r}")

        if svc.get("pull_policy") != "never":
            problems.append(f"{where}: pull_policy must be 'never' so no image is ever downloaded")

        if "build" in svc:
            problems.append(f"{where}: building images locally is not allowed")

        network_mode = svc.get("network_mode")
        if network_mode:
            problems.append(f"{where}: network_mode {network_mode!r} is not allowed")

        for key in FORBIDDEN_SERVICE_KEYS:
            if svc.get(key):
                problems.append(f"{where}: '{key}' is not allowed")

        for port in svc.get("ports") or []:
            host_ip = port.get("host_ip") if isinstance(port, dict) else None
            if host_ip not in ALLOWED_HOST_IPS:
                problems.append(f"{where}: published port must bind to 127.0.0.1, found {host_ip!r}")

        for vol in svc.get("volumes") or []:
            if not isinstance(vol, dict):
                problems.append(f"{where}: unrecognised volume entry {vol!r}")
                continue
            if vol.get("type") != "volume":
                problems.append(f"{where}: only named volumes are allowed, found type {vol.get('type')!r} ({vol.get('source')!r})")
            elif not str(vol.get("source", "")).startswith(RESOURCE_PREFIX):
                problems.append(f"{where}: volume source must start with '{RESOURCE_PREFIX}', found {vol.get('source')!r}")

    for key, vol in (config.get("volumes") or {}).items():
        vol = vol or {}
        if vol.get("external"):
            problems.append(f"volume '{key}': external volumes are not allowed")
        name = vol.get("name", key)
        if not str(name).startswith(RESOURCE_PREFIX):
            problems.append(f"volume '{key}': name must start with '{RESOURCE_PREFIX}', found {name!r}")

    for key, net in (config.get("networks") or {}).items():
        net = net or {}
        if net.get("external"):
            problems.append(f"network '{key}': external networks are not allowed")
        name = net.get("name", key)
        if not str(name).startswith(RESOURCE_PREFIX):
            problems.append(f"network '{key}': name must start with '{RESOURCE_PREFIX}', found {name!r}")

    return problems


def main(argv: list[str]) -> int:
    try:
        if len(argv) > 1:
            with open(argv[1], encoding="utf-8") as fh:
                config = json.load(fh)
        else:
            config = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"docker-scope: cannot read Compose JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(config, dict):
        print("docker-scope: Compose JSON must be an object", file=sys.stderr)
        return 2

    problems = check(config)
    if problems:
        print("docker-scope: FAIL - this configuration could affect non-SAMAY Docker resources:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("docker-scope: OK - every Compose resource is isolated to project 'samay'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
