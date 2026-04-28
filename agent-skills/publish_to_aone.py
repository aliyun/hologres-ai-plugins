#!/usr/bin/env python3
"""Publish agent skills to Aone (contextlab) platform.

Usage::

    # Publish all skills
    python publish_to_aone.py

    # Publish a specific skill
    python publish_to_aone.py --skill hologres-cli

    # Dry-run (preview without publishing)
    python publish_to_aone.py --dry-run

    # Bump patch version before publishing
    python publish_to_aone.py --bump

    # Bump to a specific version
    python publish_to_aone.py --version 1.2.0

    # Custom API URL
    python publish_to_aone.py --api-url https://custom.example.com/api/skills
"""

import argparse
import base64
import io
import json
import re
import sys
import tarfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"

API_URL = "https://contextlab.alibaba-inc.com/api/skills"
ICON_URL = "https://hologres-log-viewer.aliyun-inc.com/logo192.png"
PLATFORM = "holomcp"

# Files/dirs to exclude from tgz
EXCLUDE_NAMES = {"tests", "__pycache__", ".pyc", "pyproject.toml", ".pytest_cache"}


def parse_frontmatter(skill_md_path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from SKILL.md using simple string parsing.

    Returns dict with 'name' and 'description' keys.
    """
    text = skill_md_path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        raise ValueError(f"No frontmatter found in {skill_md_path}")

    frontmatter = m.group(1)
    result = {}

    # Parse name
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    if name_match:
        result["name"] = name_match.group(1).strip()

    # Parse description (handles multi-line YAML block scalar with |)
    desc_match = re.search(
        r"^description:\s*\|?\s*\n((?:\s+.+\n?)*)", frontmatter, re.MULTILINE
    )
    if desc_match:
        lines = desc_match.group(1).strip().splitlines()
        result["description"] = " ".join(line.strip() for line in lines)

    return result


def read_version(skill_dir: Path) -> str:
    """Read version from VERSION file, defaulting to '1.0.0'."""
    version_file = skill_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "1.0.0"


def write_version(skill_dir: Path, version: str) -> None:
    """Write version to VERSION file."""
    version_file = skill_dir / "VERSION"
    version_file.write_text(version + "\n", encoding="utf-8")


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


def generate_package_json(
    skill_dir: Path, name: str, version: str, description: str
) -> dict:
    """Generate and write package.json to skill directory. Returns the dict."""
    pkg = {
        "name": name,
        "version": version,
        "description": description,
        "publishConfig": {
            "registry": "https://contextlab.alibaba-inc.com/skill",
        },
        "aoneKit": {
            "generated": True,
        },
    }

    pkg_path = skill_dir / "package.json"
    pkg_path.write_text(
        json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return pkg


def _should_exclude(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Filter function for tarfile to exclude unwanted files."""
    name = Path(tarinfo.name).name
    parts = Path(tarinfo.name).parts

    # Exclude by exact name
    if name in EXCLUDE_NAMES:
        return None

    # Exclude by directory name in path
    for part in parts:
        if part in EXCLUDE_NAMES:
            return None

    # Exclude .pyc files
    if name.endswith(".pyc"):
        return None

    return tarinfo


def create_tgz(skill_dir: Path) -> str:
    """Create a tgz archive of the skill directory, return base64-encoded string."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(skill_dir), arcname=skill_dir.name, filter=_should_exclude)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def publish_skill(
    name: str, version: str, data_b64: str, package_json: dict, api_url: str
) -> bool:
    """POST skill to Aone API. Returns True on success."""
    body = {
        "tag": "latest",
        "data": data_b64,
        "packageJson": {
            "name": package_json["name"],
            "version": package_json["version"],
        },
        "ignoreInputPackageJson": True,
        "config": {
            "platform": PLATFORM,
            "displayName": None,
            "iconUrl": ICON_URL,
            "scopes": None,
        },
    }

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=60) as resp:
            resp_body = json.loads(resp.read().decode("utf-8"))
            rev = resp_body.get("rev", "unknown")
            saved_config = resp_body.get("savedConfig")
            print(f"  Published {name}@{version} (rev: {rev})")
            if saved_config:
                print(f"  savedConfig: {json.dumps(saved_config)}")
            return True
    except HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        print(f"  ERROR: HTTP {e.code} — {error_body}")
        return False
    except URLError as e:
        print(f"  ERROR: Network error — {e.reason}")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish agent skills to Aone (contextlab) platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python publish_to_aone.py                          # Publish all skills
  python publish_to_aone.py --skill hologres-cli     # Publish one skill
  python publish_to_aone.py --dry-run                # Preview only
  python publish_to_aone.py --bump                   # Bump patch version
  python publish_to_aone.py --version 1.2.0          # Set specific version
        """,
    )
    parser.add_argument(
        "--skill",
        help="Publish only the specified skill (by directory name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview package.json and request body without publishing",
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
        "--api-url",
        default=API_URL,
        help=f"API endpoint URL (default: {API_URL})",
    )

    args = parser.parse_args()

    skills = discover_skills(SKILLS_DIR, args.skill)
    print(f"Skills to publish: {[s.name for s in skills]}")
    print()

    success_count = 0
    fail_count = 0

    for skill_dir in skills:
        print(f"--- {skill_dir.name} ---")

        # Read metadata from SKILL.md
        try:
            meta = parse_frontmatter(skill_dir / "SKILL.md")
        except (ValueError, FileNotFoundError) as e:
            print(f"  ERROR: Failed to read SKILL.md — {e}")
            fail_count += 1
            print()
            continue

        name = meta.get("name", skill_dir.name)
        description = meta.get("description", "")

        # Determine version
        version = read_version(skill_dir)

        if args.bump:
            version = bump_patch(version)
            write_version(skill_dir, version)
            print(f"  Bumped version to {version}")
        elif args.set_version:
            version = args.set_version
            write_version(skill_dir, version)
            print(f"  Set version to {version}")

        # Generate and write package.json
        pkg = generate_package_json(skill_dir, name, version, description)
        print(f"  Generated package.json: {name}@{version}")

        # Create tgz
        data_b64 = create_tgz(skill_dir)
        tgz_size_kb = len(base64.b64decode(data_b64)) / 1024
        print(f"  Created tgz: {tgz_size_kb:.1f} KB")

        if args.dry_run:
            print("  [dry-run] Would POST to:", args.api_url)
            print(f"  [dry-run] packageJson: {json.dumps(pkg, indent=2)}")
            success_count += 1
        else:
            if publish_skill(name, version, data_b64, pkg, args.api_url):
                success_count += 1
            else:
                fail_count += 1

        print()

    # Summary
    total = success_count + fail_count
    print("=" * 40)
    if args.dry_run:
        print(f"Dry-run complete: {success_count}/{total} skills previewed")
    else:
        print(f"Published: {success_count}/{total} skills")
        if fail_count > 0:
            print(f"Failed: {fail_count}/{total} skills")
            sys.exit(1)


if __name__ == "__main__":
    main()
