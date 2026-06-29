#!/usr/bin/env python3
"""
Pre-commit guard: keep uv.lock in sync with pyproject.toml dependency changes.

Problem this prevents
---------------------
Editing dependency declarations in pyproject.toml (adding/removing/upgrading a
dep, changing a tool.uv source/index, ...) without re-running `uv lock` and
staging the updated uv.lock. The lock drifts from the manifest, so CI and other
contributors resolve a different transitive dependency tree than the author —
the classic "works on my machine" build failure. This repo was bitten by exactly
that: STS/metric/instance-manage features added alibabacloud_* deps to
pyproject.toml but the regenerated uv.lock was missed in the commit.

How it works
------------
For every *staged* pyproject.toml that sits next to a *tracked* uv.lock, extract
the dependency-bearing sections from both the staged and HEAD versions of the
file and compare them. If they differ (i.e. the dependency sections changed) but
the sibling uv.lock is NOT also staged, fail. Metadata-only edits (version,
description, authors, README, classifiers, scripts, ...) leave the extracted
sections identical and pass through without forcing a lock update.

The comparison is intentionally over the *full* file text rather than the git
diff: a diff is a local view (only a few context lines around each hunk), so it
cannot reliably tell which `[section]` a changed array item belongs to. Reading
both complete versions and reducing each to its dependency fingerprint sidesteps
that entirely.

Implementation note
-------------------
Uses plain-text parsing rather than tomllib, deliberately. The pre-commit hook
invokes the system `python3`, which on developer machines (e.g. macOS system
python <3.11) may predate the tomllib stdlib. `re`/`subprocess`/`sys` exist on
every Python 3, so the guard stays version-agnostic.

Bypass: `git commit --no-verify`.
"""

import re
import subprocess
import sys

# Whole tables whose ANY content change implies a lock update is needed.
SENSITIVE_FULL_SECTIONS = (
    "[project.optional-dependencies",
    "[project.dependency-groups",
    "[tool.uv",
    "[build-system",
)
# Keys under the bare [project] table that count as dependency-bearing.
SENSITIVE_KEYS = ("dependencies", "optional-dependencies", "dependency-groups")

HEADER_RE = re.compile(r"^\s*(\[[^\]]+\])")
KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def staged_name_status():
    """Return [(status, path), ...] for staged changes (status like A/M/D/R)."""
    rc, out = git("diff", "--cached", "--name-status")
    if rc != 0:
        return []
    pairs = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        # Rename rows look like "R100\told\tnew"; the final column is the path
        pairs.append((parts[0], parts[-1]))
    return pairs


def staged_paths():
    rc, out = git("diff", "--cached", "--name-only")
    return set(out.splitlines()) if rc == 0 else set()


def tracked_paths():
    rc, out = git("ls-files")
    return set(out.splitlines()) if rc == 0 else set()


def read_blob(ref):
    """ref like ':path' (index) or 'HEAD:path'. Returns text or '' if missing."""
    rc, out = git("show", ref)
    return out if rc == 0 else ""


def extract_dependency_fingerprint(text):
    """Reduce a pyproject.toml to its dependency-bearing lines (a comparable key).

    Walks the full text tracking the current table header and the active key;
    emits any line that falls under a dependency-bearing table
    ([project.optional-dependencies], [project.dependency-groups], [tool.uv.*],
    [build-system]) or under [project]'s dependencies / optional-dependencies /
    dependency-groups keys. Identical input sections → identical fingerprint, so
    metadata-only edits compare equal and do not trigger the guard.
    """
    if not text:
        return ""
    emitted = []
    section = None
    key = None
    for line in text.splitlines():
        hm = HEADER_RE.match(line)
        if hm:
            section = hm.group(1)
            key = None  # entering a new table resets the active key
            continue
        km = KEY_RE.match(line)
        if km:
            key = km.group(1)
        if section and any(section.startswith(p) for p in SENSITIVE_FULL_SECTIONS):
            emitted.append(line.strip())
        elif section == "[project]" and key in SENSITIVE_KEYS:
            emitted.append(line.strip())
    return "\n".join(emitted)


def dependency_changed(path):
    """True if the dependency-bearing sections differ between HEAD and index."""
    before = extract_dependency_fingerprint(read_blob(f"HEAD:{path}"))
    after = extract_dependency_fingerprint(read_blob(f":{path}"))
    return before != after


def sibling_lock(pyproject_path):
    """Return the uv.lock path next to pyproject_path ('' for repo root)."""
    directory = pyproject_path.rsplit("/", 1)[0] if "/" in pyproject_path else ""
    return f"{directory}/uv.lock" if directory else "uv.lock"


def main():
    tracked = tracked_paths()
    staged = staged_paths()

    violations = []
    for status, path in staged_name_status():
        if not path.endswith("pyproject.toml"):
            continue
        if status == "D":
            continue  # pyproject deleted — nothing to keep in sync
        lock = sibling_lock(path)
        if lock not in tracked:
            continue  # not a uv-managed package (e.g. skill template pyproject)
        if not dependency_changed(path):
            continue  # dependency sections untouched — metadata-only change

        if lock not in staged:
            violations.append((path, lock))

    if not violations:
        return 0

    print("✗ uv.lock 与 pyproject.toml 依赖变更不同步\n", file=sys.stderr)
    for pyproject, lock in violations:
        print(f"  {pyproject} 的依赖声明已修改，但未一并暂存 {lock}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "依赖声明变更后必须同步 lock，否则 CI/协作者 `uv sync` 解析出的传递依赖",
        file=sys.stderr,
    )
    print("版本会与本机不一致。\n", file=sys.stderr)
    print("请同步并暂存 lock 后再提交：", file=sys.stderr)
    for _, lock in violations:
        directory = lock.rsplit("/", 1)[0] if "/" in lock else ""
        cd = f"cd {directory} && " if directory else ""
        back = " && cd .." if directory else ""
        print(f"    {cd}uv lock{back} && git add {lock}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "若本次确属元数据改动（version/description 等，不涉及依赖），可临时绕过：",
        file=sys.stderr,
    )
    print("    git commit --no-verify", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
