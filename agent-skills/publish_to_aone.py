#!/usr/bin/env python3
"""Publish agent skills to Aone (contextlab) platform.

Reads skill metadata (name, version, description) from each skill's
package.json file. If a skill has no package.json, one is automatically
generated from the SKILL.md YAML frontmatter and written to disk.

Requires AONE_TOKEN environment variable for authentication::

    export AONE_TOKEN=<your-token>

Usage::

    # Publish all skills
    python publish_to_aone.py

    # Publish a specific skill
    python publish_to_aone.py --skill hologres-cli

    # Dry-run (preview without publishing)
    python publish_to_aone.py --dry-run

    # Bump patch version in package.json before publishing
    python publish_to_aone.py --bump

    # Set a specific version in package.json before publishing
    python publish_to_aone.py --version 1.2.0

    # Custom API URL
    python publish_to_aone.py --api-url https://custom.example.com/api/skills
"""

import argparse
import base64
import io
import json
import os
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


def parse_skill_md_frontmatter(skill_dir: Path) -> dict:
    """Parse YAML frontmatter from SKILL.md to extract name and description.

    Uses simple string parsing to avoid requiring pyyaml.
    """
    fallback = {"name": skill_dir.name, "description": ""}
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return fallback

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return fallback

    end = content.find("---", 3)
    if end == -1:
        return fallback

    frontmatter = content[3:end]
    result = dict(fallback)

    # Extract name (single-line value)
    m = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    if m:
        result["name"] = m.group(1).strip()

    # Extract description (supports multiline YAML | syntax)
    m = re.search(r"^description:\s*(.*)$", frontmatter, re.MULTILINE)
    if m:
        first_line = m.group(1).strip()
        if first_line == "|" or first_line == ">":
            # Collect indented continuation lines
            lines = []
            for line in frontmatter[m.end():].splitlines():
                if line and not line[0].isspace():
                    break
                lines.append(line.strip())
            result["description"] = " ".join(l for l in lines if l)
        elif first_line:
            result["description"] = first_line

    return result


def generate_package_json(skill_dir: Path) -> dict:
    """Generate a package.json from SKILL.md frontmatter and write it to disk."""
    meta = parse_skill_md_frontmatter(skill_dir)
    pkg = {
        "name": meta["name"],
        "version": "1.0.0",
        "description": meta["description"],
        "publishConfig": {
            "registry": "https://contextlab.alibaba-inc.com/skill"
        },
        "aoneKit": {
            "generated": True
        },
    }
    pkg_path = skill_dir / "package.json"
    pkg_path.write_text(
        json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return pkg


def read_package_json(skill_dir: Path) -> dict:
    """Read package.json from skill directory. Generate one if missing."""
    pkg_path = skill_dir / "package.json"
    if pkg_path.exists():
        return json.loads(pkg_path.read_text(encoding="utf-8"))
    return generate_package_json(skill_dir)


def update_package_json_version(skill_dir: Path, version: str) -> None:
    """Update only the version field in package.json, preserving all other fields."""
    pkg_path = skill_dir / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    pkg["version"] = version
    pkg_path.write_text(
        json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


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
    name: str, version: str, data_b64: str, package_json: dict, api_url: str,
    token: str,
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
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(
        api_url,
        data=payload,
        headers=headers,
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
        help="Auto-increment patch version in package.json before publishing",
    )
    version_group.add_argument(
        "--version",
        dest="set_version",
        help="Set a specific version in package.json before publishing (e.g., 1.2.0)",
    )
    parser.add_argument(
        "--api-url",
        default=API_URL,
        help=f"API endpoint URL (default: {API_URL})",
    )

    args = parser.parse_args()

    aone_token = os.environ.get("AONE_TOKEN", "")
    if not aone_token and not args.dry_run:
        print("ERROR: AONE_TOKEN environment variable is not set.")
        print("Please set it: export AONE_TOKEN=<your-token>")
        sys.exit(1)

    skills = discover_skills(SKILLS_DIR, args.skill)
    print(f"Skills to publish: {[s.name for s in skills]}")
    print()

    success_count = 0
    fail_count = 0

    for skill_dir in skills:
        print(f"--- {skill_dir.name} ---")

        # Read metadata from package.json (auto-generated if missing)
        pkg_existed = (skill_dir / "package.json").exists()
        try:
            pkg = read_package_json(skill_dir)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ERROR: Failed to read package.json — {e}")
            fail_count += 1
            print()
            continue

        if not pkg_existed:
            print(f"  Generated package.json from SKILL.md frontmatter")

        name = pkg.get("name", skill_dir.name)
        description = pkg.get("description", "")
        version = pkg.get("version", "1.0.0")

        if args.bump:
            version = bump_patch(version)
            update_package_json_version(skill_dir, version)
            pkg["version"] = version
            print(f"  Bumped version to {version}")
        elif args.set_version:
            version = args.set_version
            update_package_json_version(skill_dir, version)
            pkg["version"] = version
            print(f"  Set version to {version}")

        print(f"  Using package.json: {name}@{version}")

        # Create tgz
        data_b64 = create_tgz(skill_dir)
        tgz_size_kb = len(base64.b64decode(data_b64)) / 1024
        print(f"  Created tgz: {tgz_size_kb:.1f} KB")

        if args.dry_run:
            print("  [dry-run] Would POST to:", args.api_url)
            print(f"  [dry-run] packageJson: {json.dumps(pkg, indent=2)}")
            success_count += 1
        else:
            if publish_skill(name, version, data_b64, pkg, args.api_url, aone_token):
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
