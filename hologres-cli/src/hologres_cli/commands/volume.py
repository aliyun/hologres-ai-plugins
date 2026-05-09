"""Volume management commands for Hologres CLI.

Manages local volume configurations stored in profile.
Volumes are local-only (stored in config.json), not on Hologres server.
OSS file operations (list-files, delete-file, download-file, upload-file)
use oss2 SDK with access-key/access-secret stored in volume config.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from urllib.parse import urlparse

import click
import oss2

from ..config_store import (
    load_config,
    save_config,
)
from ..output import FORMAT_JSON, error, print_output, success, success_rows


# Volume name: must start with letter, only letters/digits/underscores, max 64 chars
VOLUME_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")

# Common --net option for all OSS file operations
_net_option = click.option(
    "--net", type=click.Choice(["internet", "intranet"]),
    default="internet",
    help="Network type: internet (public, default) or intranet (internal)",
)


def _parse_oss_root(root: str) -> tuple[str, str]:
    """Parse OSS root path into (bucket_name, prefix).

    Example: 'oss://bucket1/your/path/' -> ('bucket1', 'your/path/')
    """
    parsed = urlparse(root)
    bucket = parsed.hostname or ""
    prefix = parsed.path.lstrip("/")
    return bucket, prefix


def _get_oss_client(volume: dict, net: str = "internet"):
    """Create OSS Bucket client from volume config.

    Args:
        volume: volume config dict
        net: "internet" uses public_endpoint, "intranet" uses endpoint

    Returns: (oss2.Bucket, root_prefix)
    """
    ak = volume["access_key"]
    sk = volume["access_secret"]
    endpoint = volume.get("public_endpoint", "") if net == "internet" else volume["endpoint"]
    auth = oss2.Auth(ak, sk)
    bucket_name, prefix = _parse_oss_root(volume["root"])
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    return bucket, prefix


def _format_local_time(ts):
    """Convert Unix timestamp to local time ISO8601 string."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts).astimezone().isoformat()
    return str(ts)


def _build_paths(volume_name: str, file_name: str, vol: dict) -> dict:
    """Build volume_path and oss_path for a file."""
    bucket, root_prefix = _parse_oss_root(vol["root"])
    return {
        "volume_path": f"volume://{volume_name}/{file_name}",
        "oss_path": f"oss://{bucket}/{root_prefix}{file_name}",
    }


def _find_volume(volumes: list[dict], volume_name: str, fmt: str) -> dict | None:
    """Find a volume by name. Returns volume dict or None (prints error)."""
    for v in volumes:
        if v["name"] == volume_name:
            return v
    print_output(error(
        "NOT_FOUND",
        f"Volume '{volume_name}' not found.",
        fmt,
    ))
    return None


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
@click.option("--access-key", required=True,
              help="OSS AccessKey ID for SDK operations")
@click.option("--access-secret", required=True,
              help="OSS AccessKey Secret for SDK operations")
@click.pass_context
def create_cmd(
    ctx: click.Context,
    volume_name: str,
    vol_type: str,
    endpoint: str,
    root: str,
    rolearn: str,
    access_key: str,
    access_secret: str,
) -> None:
    """Create a volume configuration in current profile.

    \b
    Examples:
      hologres volume create my_vol --type oss \\
        --endpoint oss-cn-hangzhou-internal.aliyuncs.com \\
        --root oss://bucket/path/ \\
        --rolearn acs:ram::123456:role/AliyunHologresDefaultRole \\
        --access-key LTAI5tXxx --access-secret xxxx
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

    # Auto-generate public endpoint from internal endpoint
    public_endpoint = endpoint.replace("-internal", "")

    # Create OSS directory placeholder before saving config
    try:
        bucket, root_prefix = _get_oss_client(
            {"access_key": access_key, "access_secret": access_secret,
             "public_endpoint": public_endpoint, "endpoint": endpoint,
             "root": root},
            net="internet",
        )
        if root_prefix:
            bucket.put_object(root_prefix, b"")
    except Exception as exc:
        print_output(error(
            "OSS_ERROR",
            f"Failed to create OSS directory placeholder: {exc}",
            fmt,
        ))
        return

    # OSS placeholder created, now save config
    volume_entry = {
        "name": volume_name,
        "type": vol_type,
        "endpoint": endpoint,
        "public_endpoint": public_endpoint,
        "root": root,
        "rolearn": rolearn,
        "access_key": access_key,
        "access_secret": access_secret,
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


@volume_cmd.command("list-files")
@click.option("--volume", "volume_name", required=True, help="Volume name")
@click.option("--prefix", default="", help="Filter by prefix")
@click.option("--max-count", default=100, type=int,
              help="Max files to list (default: 100)")
@_net_option
@click.pass_context
def list_files_cmd(
    ctx: click.Context,
    volume_name: str,
    prefix: str,
    max_count: int,
    net: str,
) -> None:
    """List files in a volume via OSS SDK.

    \b
    Examples:
      hologres volume list-files --volume my_vol
      hologres volume list-files --volume my_vol --prefix data/
      hologres volume list-files --volume my_vol --max-count 50
      hologres volume list-files --volume my_vol --net intranet
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    vol = _find_volume(volumes, volume_name, fmt)
    if vol is None:
        return

    try:
        bucket, root_prefix = _get_oss_client(vol, net)
        full_prefix = root_prefix + prefix
        rows = []
        count = 0
        for obj in oss2.ObjectIterator(bucket, prefix=full_prefix, max_keys=max_count):
            if obj.key.endswith("/"):
                continue
            rel_name = obj.key
            if rel_name.startswith(root_prefix):
                rel_name = rel_name[len(root_prefix):]
            paths = _build_paths(volume_name, rel_name, vol)
            rows.append({
                "name": rel_name,
                "volume_path": paths["volume_path"],
                "oss_path": paths["oss_path"],
                "size": obj.size,
                "last_modified": _format_local_time(obj.last_modified),
            })
            count += 1
            if count >= max_count:
                break
    except oss2.exceptions.OssError as e:
        print_output(error("OSS_ERROR", str(e), fmt))
        return

    print_output(success_rows(rows, fmt))


@volume_cmd.command("delete-file")
@click.option("--volume", "volume_name", required=True, help="Volume name")
@click.option("--file", "file_name", required=True,
              help="File path relative to volume root")
@click.option("--confirm", is_flag=True,
              help="Confirm deletion (dry-run without this)")
@_net_option
@click.pass_context
def delete_file_cmd(
    ctx: click.Context,
    volume_name: str,
    file_name: str,
    confirm: bool,
    net: str,
) -> None:
    """Delete a file from OSS volume.

    Defaults to dry-run for safety. Use --confirm to actually delete.

    \b
    Examples:
      hologres volume delete-file --volume my_vol --file data/report.csv
      hologres volume delete-file --volume my_vol --file data/report.csv --confirm
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    vol = _find_volume(volumes, volume_name, fmt)
    if vol is None:
        return

    _, root_prefix = _parse_oss_root(vol["root"])
    full_key = root_prefix + file_name

    if not confirm:
        paths = _build_paths(volume_name, file_name, vol)
        print_output(success({
            "action": f"DELETE oss://{_parse_oss_root(vol['root'])[0]}/{full_key}",
            "volume_path": paths["volume_path"],
            "oss_path": paths["oss_path"],
            "dry_run": True,
        }, fmt))
        return

    try:
        bucket, _ = _get_oss_client(vol, net)
        bucket.delete_object(full_key)
    except oss2.exceptions.OssError as e:
        print_output(error("OSS_ERROR", str(e), fmt))
        return

    paths = _build_paths(volume_name, file_name, vol)
    print_output(success({
        "file": file_name,
        "volume_path": paths["volume_path"],
        "oss_path": paths["oss_path"],
        "deleted": True,
    }, fmt))


@volume_cmd.command("download-file")
@click.option("--volume", "volume_name", required=True, help="Volume name")
@click.option("--file", "file_name", required=True,
              help="File path relative to volume root")
@click.option("--download-dir", "-d", required=True,
              help="Local directory to save file")
@_net_option
@click.pass_context
def download_file_cmd(
    ctx: click.Context,
    volume_name: str,
    file_name: str,
    download_dir: str,
    net: str,
) -> None:
    """Download a file from OSS volume to local directory.

    \b
    Examples:
      hologres volume download-file --volume my_vol --file report.csv -d ./output
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    vol = _find_volume(volumes, volume_name, fmt)
    if vol is None:
        return

    # Ensure download dir exists
    os.makedirs(download_dir, exist_ok=True)

    _, root_prefix = _parse_oss_root(vol["root"])
    full_key = root_prefix + file_name
    local_filename = os.path.basename(file_name)
    local_path = os.path.join(download_dir, local_filename)

    try:
        bucket, _ = _get_oss_client(vol, net)
        bucket.get_object_to_file(full_key, local_path)
    except oss2.exceptions.OssError as e:
        print_output(error("OSS_ERROR", str(e), fmt))
        return

    paths = _build_paths(volume_name, file_name, vol)
    print_output(success({
        "file": file_name,
        "volume_path": paths["volume_path"],
        "oss_path": paths["oss_path"],
        "local_path": local_path,
        "downloaded": True,
    }, fmt))


@volume_cmd.command("upload-file")
@click.option("--volume", "volume_name", required=True, help="Volume name")
@click.option("--local-file", required=True, help="Local file path to upload")
@click.option("--target-file", required=True,
              help="Target file path relative to volume root")
@_net_option
@click.pass_context
def upload_file_cmd(
    ctx: click.Context,
    volume_name: str,
    local_file: str,
    target_file: str,
    net: str,
) -> None:
    """Upload a local file to OSS volume.

    \b
    Examples:
      hologres volume upload-file --volume my_vol --local-file ./data.csv --target-file data/data.csv
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if not os.path.isfile(local_file):
        print_output(error(
            "FILE_NOT_FOUND",
            f"Local file '{local_file}' not found.",
            fmt,
        ))
        return

    config = load_config()
    target_profile = _find_profile(config, profile_name, fmt)
    if target_profile is None:
        return

    volumes = target_profile.get("volumes", [])
    vol = _find_volume(volumes, volume_name, fmt)
    if vol is None:
        return

    _, root_prefix = _parse_oss_root(vol["root"])
    full_key = root_prefix + target_file

    try:
        bucket, _ = _get_oss_client(vol, net)
        bucket.put_object_from_file(full_key, local_file)
    except oss2.exceptions.OssError as e:
        print_output(error("OSS_ERROR", str(e), fmt))
        return

    paths = _build_paths(volume_name, target_file, vol)
    print_output(success({
        "local_file": local_file,
        "target_file": target_file,
        "volume_path": paths["volume_path"],
        "oss_path": paths["oss_path"],
        "uploaded": True,
    }, fmt))


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
