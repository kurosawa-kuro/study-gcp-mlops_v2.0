#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import compose, step


def main() -> None:
    step("Seeding PostgreSQL")
    compose(["run", "--rm", "--build", "seed"])


if __name__ == "__main__":
    main()
