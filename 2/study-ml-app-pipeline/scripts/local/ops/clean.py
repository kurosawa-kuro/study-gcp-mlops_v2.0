#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import compose, project_root, run, step


def main() -> None:
    root = project_root()
    step("Cleaning")
    compose(["down", "--remove-orphans", "--volumes"], check=False)

    models_dir = root / "ml" / "registry" / "artifacts"
    if models_dir.exists():
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{models_dir}:/work/models",
                "alpine",
                "sh",
                "-c",
                "rm -rf /work/models/*",
            ],
            check=False,
        )
    print("Done.")


if __name__ == "__main__":
    main()
