#!/usr/bin/env python3
"""Sync skills into the package, run ``uv build``, then remove the copy.

Run from the ``agent-skills`` directory::

    uv run upload_to_pypi.py

Requires ``uv`` on PATH: https://docs.astral.sh/uv/
"""
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    src = root / "skills"
    dst = root / "src" / "holo_plugin_installer" / "skills"

    if not src.exists():
        raise SystemExit("skills/ directory not found in project root. Please create it first.")

    uv = shutil.which("uv")
    if not uv:
        raise SystemExit(
            "uv is not installed or not on PATH. See https://docs.astral.sh/uv/"
        )

    # 1. Sync skills -> package
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    print("Synced skills/ -> src/holo_plugin_installer/skills/")

    try:
        # 2. Build wheel (PEP 517 via uv)
        print("Building wheel (uv build)...")
        subprocess.run(
            [uv, "build"],
            cwd=root,
            check=True,
        )
    finally:
        # 3. Remove skills from package (restore to only project root)
        if dst.exists():
            shutil.rmtree(dst)
            print("Removed src/holo_plugin_installer/skills/")

    print("Build complete, artifacts in dist/")


if __name__ == "__main__":
    main()
