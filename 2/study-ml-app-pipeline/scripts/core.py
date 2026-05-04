#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return ROOT


def step(message: str) -> None:
    print(f"=== {message} ===")


def load_credentials() -> None:
    yaml_path = ROOT / "env" / "secret" / "credential.yaml"
    if not yaml_path.exists():
        return

    for raw_line in yaml_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key.upper()] = value


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> int:
    completed = subprocess.run(command, cwd=cwd or ROOT, check=False)
    if check and completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.returncode


HOST_PORTS = (5432, 8000)
OWN_CONTAINER_PREFIX = "study-ml-app-pipeline-"


def free_host_ports(ports: tuple[int, ...] = HOST_PORTS) -> None:
    for port in ports:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return
        names = [
            name
            for name in result.stdout.splitlines()
            if name and not name.startswith(OWN_CONTAINER_PREFIX)
        ]
        for name in names:
            step(f"Freeing host :{port} (removing {name})")
            subprocess.run(["docker", "rm", "-f", name], check=False)


def compose(args: list[str], *, check: bool = True) -> int:
    load_credentials()
    if args and args[0] in {"up", "run"}:
        free_host_ports()
    return run(["docker", "compose", *args], check=check)


def python_bin() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable
