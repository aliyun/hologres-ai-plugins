#!/usr/bin/env python3
"""Build and upload hologres-cli to PyPI using uv.

Usage::

    # Build only (artifacts in dist/)
    python upload_to_pypi.py --build

    # Upload to TestPyPI (dry-run verification)
    python upload_to_pypi.py --test

    # Upload to official PyPI
    python upload_to_pypi.py --publish

    # Bump version, build, and publish
    python upload_to_pypi.py --publish --version 1.1.0

    # Skip tests before publishing
    python upload_to_pypi.py --publish --skip-tests

Requires:
    - uv (https://docs.astral.sh/uv/)
    - PyPI API token: set UV_PUBLISH_TOKEN env var or --token flag
    - TestPyPI token: set TEST_PYPI_TOKEN env var (for --test mode)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
DIST = ROOT / "dist"


# ── helpers ─────────────────────────────────────────────────────────

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, print it, and check for errors."""
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def require_uv() -> str:
    """Return path to uv binary or exit."""
    uv = shutil.which("uv")
    if not uv:
        print("ERROR: uv is not installed or not on PATH.")
        print("Install: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print("Docs:    https://docs.astral.sh/uv/")
        sys.exit(1)
    return uv


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        print("ERROR: Cannot find version in pyproject.toml")
        sys.exit(1)
    return m.group(1)


def set_version(new_version: str) -> None:
    """Update version in pyproject.toml."""
    text = PYPROJECT.read_text()
    old = get_current_version()
    updated = text.replace(f'version = "{old}"', f'version = "{new_version}"')
    PYPROJECT.write_text(updated)
    print(f"Version: {old} -> {new_version}")


# ── stages ──────────────────────────────────────────────────────────

def stage_test(uv: str) -> None:
    """Run unit tests to ensure quality before publishing."""
    print("\n" + "=" * 60)
    print("STAGE: Running tests")
    print("=" * 60)
    run(
        [uv, "run", "pytest", "tests/", "--ignore=tests/integration", "-q"],
        cwd=ROOT,
    )
    print("All tests passed.")


def stage_clean() -> None:
    """Remove old build artifacts."""
    if DIST.exists():
        shutil.rmtree(DIST)
        print("Cleaned dist/")
    for d in ROOT.glob("src/*.egg-info"):
        shutil.rmtree(d)
        print(f"Cleaned {d.name}")


def stage_build(uv: str) -> None:
    """Build sdist + wheel via uv build."""
    print("\n" + "=" * 60)
    print("STAGE: Building package")
    print("=" * 60)
    run([uv, "build"], cwd=ROOT)

    artifacts = list(DIST.glob("*"))
    print(f"\nBuild artifacts ({len(artifacts)}):")
    for a in sorted(artifacts):
        size_kb = a.stat().st_size / 1024
        print(f"  {a.name}  ({size_kb:.1f} KB)")


def stage_publish(uv: str, token: str | None, test_pypi: bool) -> None:
    """Upload to PyPI or TestPyPI."""
    target = "TestPyPI" if test_pypi else "PyPI"
    print("\n" + "=" * 60)
    print(f"STAGE: Uploading to {target}")
    print("=" * 60)

    # Resolve token
    if not token:
        env_key = "TEST_PYPI_TOKEN" if test_pypi else "UV_PUBLISH_TOKEN"
        token = os.environ.get(env_key)
        if not token:
            print(f"ERROR: No API token provided.")
            print(f"  Set {env_key} environment variable, or use --token flag.")
            print()
            if test_pypi:
                print("  Get a TestPyPI token: https://test.pypi.org/manage/account/token/")
            else:
                print("  Get a PyPI token: https://pypi.org/manage/account/token/")
            sys.exit(1)

    cmd = [uv, "publish"]
    if test_pypi:
        cmd += [
            "--publish-url", "https://test.pypi.org/legacy/",
        ]
    cmd += ["--token", token]

    # Add all dist files
    dist_files = sorted(DIST.glob("*"))
    cmd += [str(f) for f in dist_files]

    run(cmd, cwd=ROOT)

    version = get_current_version()
    print(f"\nPublished hologres-cli {version} to {target}!")
    if test_pypi:
        print(f"  pip install -i https://test.pypi.org/simple/ hologres-cli=={version}")
    else:
        print(f"  pip install hologres-cli=={version}")


# ── main ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and upload hologres-cli to PyPI using uv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python upload_to_pypi.py --build                     # Build only
  python upload_to_pypi.py --test                      # Upload to TestPyPI
  python upload_to_pypi.py --publish                   # Upload to PyPI
  python upload_to_pypi.py --publish --version 1.1.0   # Bump version and publish
  python upload_to_pypi.py --publish --skip-tests      # Skip tests
        """,
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--build", action="store_true",
        help="Build package only (sdist + wheel)",
    )
    action.add_argument(
        "--test", action="store_true",
        help="Build and upload to TestPyPI",
    )
    action.add_argument(
        "--publish", action="store_true",
        help="Build and upload to official PyPI",
    )
    parser.add_argument(
        "--version",
        help="Set version before building (e.g., 1.1.0)",
    )
    parser.add_argument(
        "--token",
        help="PyPI API token (overrides env var)",
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Skip running tests before build",
    )

    args = parser.parse_args()
    uv = require_uv()

    print(f"hologres-cli upload script")
    print(f"Project: {ROOT}")
    print(f"Current version: {get_current_version()}")

    # Optional: bump version
    if args.version:
        set_version(args.version)

    # Run tests
    if not args.skip_tests and (args.test or args.publish):
        stage_test(uv)

    # Clean + Build
    stage_clean()
    stage_build(uv)

    # Publish
    if args.test:
        stage_publish(uv, args.token, test_pypi=True)
    elif args.publish:
        stage_publish(uv, args.token, test_pypi=False)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
