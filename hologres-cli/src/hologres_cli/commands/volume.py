"""Volume management commands for Hologres CLI.

Manages local volume configurations stored in profile.
Volumes are local-only (stored in config.json), not on Hologres server.
"""

from __future__ import annotations

import re

import click

from ..config_store import (
    load_config,
    save_config,
)
from ..output import FORMAT_JSON, error, print_output, success, success_rows


# Volume name: must start with letter, only letters/digits/underscores, max 64 chars
VOLUME_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


@click.group("volume")
def volume_cmd() -> None:
    """Manage local volume configurations (OSS file storage)."""
    pass


@volume_cmd.command("create")
@click.argument("volume_name")
@click.option("--type", "vol_type", default="oss",
              help="Volume type (currently only 'oss')")
@click.option("--endpoint", required=True,
              help="OSS internal endpoint (e.g. oss-cn-hangzhou-internal.aliyuncs.com)")
@click.option("--root", required=True,
              help="OSS root path (e.g. oss://bucket/path/)")
@click.option("--rolearn", required=True,
              help="RAM role ARN for Hologres service")
@click.pass_context
def create_cmd(
    ctx: click.Context,
    volume_name: str,
    vol_type: str,
    endpoint: str,
    root: str,
    rolearn: str,
) -> None:
    """Create a volume configuration in current profile.

    \b
    Examples:
      hologres volume create my_vol --type oss \\
        --endpoint oss-cn-hangzhou-internal.aliyuncs.com \\
        --root oss://bucket/path/ \\
        --rolearn acs:ram::123456:role/AliyunHologresDefaultRole
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Validate volume_name
    if not VOLUME_NAME_PATTERN.match(volume_name):
        print_output(error(
            "INVALID_INPUT",
            "Volume name must start with a letter, contain only letters, "
            "digits, and underscores, and be at most 64 characters.",
            fmt,
        ))
        return

    # Validate type
    if vol_type != "oss":
        print_output(error(
            "INVALID_ARGS",
            f"Unsupported volume type '{vol_type}'. Currently only 'oss' is supported.",
            fmt,
        ))
        return

    # Validate endpoint (must be OSS internal)
    if "-internal" not in endpoint:
        print_output(error(
            "INVALID_ARGS",
            "Endpoint must be an OSS internal endpoint (containing '-internal').",
            fmt,
        ))
        return

    # Validate root path
    if not root.startswith("oss://"):
        print_output(error(
            "INVALID_ARGS",
            "Root path must start with 'oss://' (e.g. oss://bucket/path/).",
            fmt,
        ))
        return
    # Auto-append trailing slash
    if not root.endswith("/"):
        root = root + "/"

    # Load config and find target profile
    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    # Check uniqueness
    volumes = target_profile.setdefault("volumes", [])
    if any(v["name"] == volume_name for v in volumes):
        print_output(error(
            "ALREADY_EXISTS",
            f"Volume '{volume_name}' already exists in profile "
            f"'{target_profile['name']}'.",
            fmt,
        ))
        return

    # Add volume and save
    volume_entry = {
        "name": volume_name,
        "type": vol_type,
        "endpoint": endpoint,
        "root": root,
        "rolearn": rolearn,
    }
    volumes.append(volume_entry)
    save_config(config)

    print_output(success({"volume": volume_name, "created": True}, fmt))


@volume_cmd.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List all volumes in current profile.

    \b
    Examples:
      hologres volume list
      hologres -f table volume list
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    rows = [
        {
            "name": v["name"],
            "type": v.get("type", ""),
            "endpoint": v.get("endpoint", ""),
            "root": v.get("root", ""),
        }
        for v in volumes
    ]

    print_output(success_rows(rows, fmt))


@volume_cmd.command("delete")
@click.argument("volume_name")
@click.pass_context
def delete_cmd(ctx: click.Context, volume_name: str) -> None:
    """Delete a volume from current profile.

    \b
    Examples:
      hologres volume delete my_vol
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    original_len = len(volumes)
    target_profile["volumes"] = [v for v in volumes if v["name"] != volume_name]

    if len(target_profile["volumes"]) == original_len:
        print_output(error(
            "NOT_FOUND",
            f"Volume '{volume_name}' not found in profile "
            f"'{target_profile['name']}'.",
            fmt,
        ))
        return

    save_config(config)
    print_output(success({"volume": volume_name, "deleted": True}, fmt))


def _find_profile(
    config: dict, profile_name: str | None, fmt: str
) -> dict | None:
    """Find target profile from config. Returns profile dict reference or None."""
    current = profile_name or config.get("current", "")
    if not current:
        print_output(error(
            "CONFIG_ERROR",
            "No current profile configured. Run 'hologres config' to set up.",
            fmt,
        ))
        return None
    for p in config.get("profiles", []):
        if p.get("name") == current:
            return p
    print_output(error(
        "CONFIG_ERROR",
        f"Profile '{current}' not found.",
        fmt,
    ))
    return None
