"""AI commands for Hologres CLI."""

from __future__ import annotations

import json as json_mod
import time

import click

from ..config_store import load_config
from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    error,
    print_output,
    query_error,
    success,
)


def _parse_volume_uri(uri: str) -> tuple[str, str]:
    """Parse volume://volume_name/sub_path -> (volume_name, sub_path).

    Raises ValueError if format is invalid.
    """
    if not uri.startswith("volume://"):
        raise ValueError(
            f"Invalid volume URI: {uri}. Expected format: volume://volume_name[/sub_path]"
        )
    path = uri[len("volume://"):]
    parts = path.split("/", 1)
    volume_name = parts[0]
    if not volume_name:
        raise ValueError("Volume name cannot be empty.")
    sub_path = parts[1] if len(parts) > 1 else ""
    return volume_name, sub_path


def _get_volume_config(profile_name: str | None, volume_name: str) -> dict | None:
    """Load volume config by name from current profile."""
    config = load_config()
    profiles = config.get("profiles", [])
    current = profile_name or config.get("current", "default")
    target = next((p for p in profiles if p["name"] == current), None)
    if not target:
        return None
    volumes = target.get("volumes", [])
    return next((v for v in volumes if v["name"] == volume_name), None)


def _build_oss_output_dir(volume_root: str, sub_path: str) -> str:
    """Combine volume root and sub_path into output_dir for JSON request body.

    Example: ('oss://bucket/path/', 'sub/dir') -> 'oss://bucket/path/sub/dir'
    """
    root = volume_root.rstrip("/")
    sub = sub_path.lstrip("/")
    if sub:
        return f"{root}/{sub}"
    return f"{root}/"


def _oss_to_volume_path(oss_path: str, volume_root: str, volume_name: str) -> str:
    """Convert OSS path to volume:// URI."""
    root = volume_root.rstrip("/")
    if oss_path.startswith(root):
        relative = oss_path[len(root):].lstrip("/")
        if relative:
            return f"volume://{volume_name}/{relative}"
        return f"volume://{volume_name}"
    return oss_path


@click.group("ai")
def ai_cmd() -> None:
    """AI commands (text generation, etc.)."""
    pass


@ai_cmd.command("gen")
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="AI model name (optional, uses server default if not specified)")
@click.pass_context
def gen_cmd(ctx: click.Context, prompt: str, model: str | None) -> None:
    """Generate text using Hologres AI function.

    \b
    Examples:
      hologres ai gen "介绍下 hologres"
      hologres ai gen "写一首关于数据库的诗" --model qwen-max
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile, read_only=True)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        if model:
            query = "SELECT ai_gen(%s, %s)"
            params = (model, prompt)
        else:
            query = "SELECT ai_gen(%s)"
            params = (prompt,)

        rows = conn.execute(query, params)

        duration_ms = (time.time() - start_time) * 1000

        result_text = ""
        if rows:
            first_row = rows[0]
            result_text = list(first_row.values())[0] or ""

        log_operation(
            "ai.gen",
            sql="SELECT ai_gen('<prompt>')",
            dsn_masked=conn.masked_dsn,
            success=True,
            duration_ms=duration_ms,
        )

        if fmt == FORMAT_JSON:
            data = {"text": result_text}
            if model:
                data["model"] = model
            print_output(success(data))
        else:
            print_output(result_text)

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "ai.gen",
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@ai_cmd.command("image-gen")
@click.argument("prompt")
@click.option("--output-dir", "-o", required=True,
              help="Output directory. volume://volume_name[/sub_path] for OSS output")
@click.option("--model", "-m", default=None, help="AI model name (e.g. qwen-image-2.0)")
@click.option("--negative-prompt", default=None, help="Negative prompt, max 500 chars")
@click.option("--size", default=None, help="Output image size, e.g. '1280*720'")
@click.option("-n", "num_images", type=int, default=None, help="Number of images to generate (1-6)")
@click.option("--prompt-extend", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Enable/disable prompt rewriting")
@click.option("--watermark", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Add watermark to image")
@click.option("--seed", type=int, default=None, help="Random seed [0, 2147483647]")
@click.pass_context
def image_gen_cmd(ctx: click.Context, prompt: str, output_dir: str,
                  model: str | None, negative_prompt: str | None,
                  size: str | None, num_images: int | None,
                  prompt_extend: str | None, watermark: str | None,
                  seed: int | None) -> None:
    """Generate images using Hologres AI function and save to OSS volume.

    \b
    Examples:
      hologres ai image-gen "生成一只可爱的猫" -o volume://my_vol/images
      hologres ai image-gen "生成一只猫" --model qwen-image-2.0 -o volume://my_vol
      hologres ai image-gen "短剧男主" --negative-prompt "低画质" -n 2 -o volume://my_vol/output
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    # Parse volume URI
    try:
        volume_name, sub_path = _parse_volume_uri(output_dir)
    except ValueError as e:
        print_output(error("INVALID_ARGS", str(e), fmt))
        return

    # Look up volume config
    volume = _get_volume_config(profile, volume_name)
    if not volume:
        print_output(error(
            "NOT_FOUND",
            f"Volume '{volume_name}' not found. Run 'hologres volume create' first.",
            fmt,
        ))
        return

    try:
        conn = get_connection(profile=profile, read_only=True)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Build JSON request body
        request: dict = {"prompt": prompt}

        if negative_prompt is not None:
            request["negative_prompt"] = negative_prompt

        parameters: dict = {}
        if size is not None:
            parameters["size"] = size
        if num_images is not None:
            parameters["n"] = num_images
        if prompt_extend is not None:
            parameters["prompt_extend"] = prompt_extend.lower() == "true"
        if watermark is not None:
            parameters["watermark"] = watermark.lower() == "true"
        if seed is not None:
            parameters["seed"] = seed

        if parameters:
            request["parameters"] = parameters

        # Add output_dir to request body
        oss_output_dir = _build_oss_output_dir(volume["root"], sub_path)
        request["output_dir"] = oss_output_dir

        request_json = json_mod.dumps(request, ensure_ascii=False)

        # Build SQL: model and to_file are orthogonal.
        # rolearn is inlined as a SQL literal instead of a bind parameter because
        # Hologres to_file() does not support PBE (Parse/Bind/Execute) protocol
        # for the rolearn argument.
        rolearn_literal = volume["rolearn"].replace("'", "''")
        if model:
            query = f"SELECT ai_gen(%s, %s, to_file(%s, %s, '{rolearn_literal}'))"
            params = (model, request_json, volume["root"], volume["endpoint"])
        else:
            query = f"SELECT ai_gen(%s, to_file(%s, %s, '{rolearn_literal}'))"
            params = (request_json, volume["root"], volume["endpoint"])

        rows = conn.execute(query, params)

        duration_ms = (time.time() - start_time) * 1000

        result_text = ""
        if rows:
            first_row = rows[0]
            result_text = list(first_row.values())[0] or ""

        log_operation(
            "ai.image-gen",
            sql="SELECT ai_gen('<image-gen-request>')",
            dsn_masked=conn.masked_dsn,
            success=True,
            duration_ms=duration_ms,
        )

        # Parse response JSON, extract image_oss_paths and usage
        oss_paths: list = []
        usage = None
        try:
            result_obj = json_mod.loads(result_text)
            oss_paths = result_obj.get("image_oss_paths", [])
            usage = result_obj.get("usage")
        except (json_mod.JSONDecodeError, TypeError):
            pass

        if fmt == FORMAT_JSON:
            if oss_paths:
                images = []
                for p in oss_paths:
                    images.append({
                        "oss_path": p,
                        "volume_path": _oss_to_volume_path(p, volume["root"], volume_name),
                    })
                data: dict = {"images": images}
                if usage:
                    data["usage"] = usage
            else:
                data = {"raw_result": result_text}
            if model:
                data["model"] = model
            print_output(success(data))
        else:
            if oss_paths:
                volume_paths = [
                    _oss_to_volume_path(p, volume["root"], volume_name)
                    for p in oss_paths
                ]
                print_output("\n".join(volume_paths))
            else:
                print_output(result_text)

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "ai.image-gen",
            dsn_masked=getattr(conn, "masked_dsn", "unknown") if conn else "unknown",
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
