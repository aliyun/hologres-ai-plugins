#!/usr/bin/env python3
"""Publish agent skills to ClawHub (OpenClaw Skill Marketplace).

ClawHub is the public skill registry for OpenClaw. Skills are published
using the `clawhub` CLI tool. Each skill contains a SKILL.md with YAML
frontmatter (name, description) and supporting reference files.

Prerequisites:
    npm i -g clawhub
    clawhub login

Usage::

    # Publish all skills
    python publish_to_clawhub.py

    # Publish a specific skill
    python publish_to_clawhub.py --skill hologres-cli

    # Dry-run (preview without publishing)
    python publish_to_clawhub.py --dry-run

    # Bump patch version before publishing
    python publish_to_clawhub.py --bump

    # Set a specific version
    python publish_to_clawhub.py --version 1.2.0

    # Publish under an org/publisher handle
    python publish_to_clawhub.py --owner holomcp
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"

# Files/dirs to exclude from published skill (tests, build config, etc.)
EXCLUDE_NAMES = {"tests", "__pycache__", ".pyc", "pyproject.toml", ".pytest_cache"}


def require_clawhub() -> str:
    """Ensure the clawhub CLI is available, return its path."""
    clawhub = shutil.which("clawhub")
    if not clawhub:
        print("ERROR: 'clawhub' CLI not found in PATH.")
        print("Install it with: npm i -g clawhub")
        print("Then authenticate: clawhub login")
        sys.exit(1)
    return clawhub


def read_version(skill_dir: Path) -> str:
    """Read version from VERSION file. Falls back to package.json, then 0.1.0."""
    version_file = skill_dir / "VERSION"
    if version_file.exists():
        ver = version_file.read_text().strip()
        if ver:
            return ver

    pkg_file = skill_dir / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
            return pkg.get("version", "0.1.0")
        except (json.JSONDecodeError, OSError):
            pass

    return "0.1.0"


def write_version(skill_dir: Path, version: str) -> None:
    """Write version to VERSION file and update package.json if exists."""
    (skill_dir / "VERSION").write_text(version + "\n")

    pkg_file = skill_dir / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
            pkg["version"] = version
            pkg_file.write_text(
                json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError):
            pass


def bump_patch(version: str) -> str:
    """Bump the patch component of a semver version string."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver: {version}")
    parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


def discover_skills(skills_dir: Path, skill_filter: str | None = None) -> list[Path]:
    """Discover skill directories under skills_dir."""
    if not skills_dir.exists():
        print(f"ERROR: skills directory not found: {skills_dir}")
        sys.exit(1)

    candidates = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )

    if skill_filter:
        matched = [d for d in candidates if d.name == skill_filter]
        if not matched:
            available = [d.name for d in candidates]
            print(f"ERROR: skill '{skill_filter}' not found. Available: {available}")
            sys.exit(1)
        return matched

    return candidates


def publish_skill(
    clawhub: str,
    skill_dir: Path,
    version: str,
    owner: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Publish a single skill using clawhub CLI. Returns True on success."""
    cmd = [clawhub, "skill", "publish", str(skill_dir), "--version", version]

    if owner:
        cmd.extend(["--owner", owner])

    if dry_run:
        print(f"  [dry-run] Would run: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Print stdout for success details
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    print(f"  {line}")
            return True
        else:
            print(f"  ERROR: clawhub publish failed (exit code {result.returncode})")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines():
                    print(f"  {line}")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    print(f"  {line}")
            return False
    except subprocess.TimeoutExpired:
        print("  ERROR: clawhub publish timed out (120s)")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish agent skills to ClawHub (OpenClaw Skill Marketplace)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python publish_to_clawhub.py                          # Publish all skills
  python publish_to_clawhub.py --skill hologres-cli     # Publish one skill
  python publish_to_clawhub.py --dry-run                # Preview only
  python publish_to_clawhub.py --bump                   # Bump patch version
  python publish_to_clawhub.py --version 1.2.0          # Set specific version
  python publish_to_clawhub.py --owner holomcp          # Publish under org
        """,
    )
    parser.add_argument(
        "--skill",
        help="Publish only the specified skill (by directory name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview commands without publishing",
    )
    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument(
        "--bump",
        action="store_true",
        help="Auto-increment patch version before publishing",
    )
    version_group.add_argument(
        "--version",
        dest="set_version",
        help="Set a specific version before publishing (e.g., 1.2.0)",
    )
    parser.add_argument(
        "--owner",
        help="Publish under an org/publisher handle (e.g., holomcp)",
    )

    args = parser.parse_args()

    # Check CLI availability (skip in dry-run for convenience)
    if not args.dry_run:
        clawhub = require_clawhub()
    else:
        clawhub = shutil.which("clawhub") or "clawhub"

    skills = discover_skills(SKILLS_DIR, args.skill)

    print("=" * 60)
    print("ClawHub Skill Publisher")
    print("=" * 60)
    print(f"Skills directory: {SKILLS_DIR}")
    print(f"Skills to publish: {[s.name for s in skills]}")
    if args.owner:
        print(f"Owner: {args.owner}")
    print()

    success_count = 0
    fail_count = 0

    for skill_dir in skills:
        version = read_version(skill_dir)

        # Version bump/set
        if args.bump:
            version = bump_patch(version)
            write_version(skill_dir, version)
        elif args.set_version:
            version = args.set_version
            write_version(skill_dir, version)

        print(f"--- {skill_dir.name} @ v{version} ---")

        if publish_skill(clawhub, skill_dir, version, args.owner, args.dry_run):
            success_count += 1
            if args.dry_run:
                print(f"  ✅ [dry-run] Ready to publish")
            else:
                print(f"  ✅ Published to ClawHub")
        else:
            fail_count += 1

        print()

    # Summary
    total = success_count + fail_count
    print("=" * 60)
    if args.dry_run:
        print(f"Dry-run complete: {success_count}/{total} skills ready")
    else:
        print(f"Published: {success_count}/{total} skills to ClawHub")
        if fail_count > 0:
            print(f"Failed: {fail_count}/{total} skills")
            sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
