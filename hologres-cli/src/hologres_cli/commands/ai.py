"""AI commands for Hologres CLI."""

from __future__ import annotations

import json as json_mod
import os
import time
import uuid

import click

from ..config_store import load_config
from ..connection import DSNError, get_connection
from ..errors import ErrorCode
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    error,
    print_output,
    query_error,
    success,
)
from .volume import _get_oss_client, _parse_oss_root, _parse_volume_uri


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


def _resolve_media_url(
    uri: str, profile: str | None, fmt: str,
    upload_volume: str | None = None,
    net: str = "internet",
) -> str | None:
    """Resolve volume://, oss://, or local file path to OSS path.

    Returns the resolved OSS path, or None on error (error already printed).
    """
    if uri.startswith("oss://"):
        return uri
    if uri.startswith("volume://"):
        try:
            vol_name, rel_path = _parse_volume_uri(uri)
        except ValueError as e:
            print_output(error("INVALID_ARGS", str(e), fmt))
            return None
        vol = _get_volume_config(profile, vol_name)
        if not vol:
            print_output(error(
                "NOT_FOUND",
                f"Volume '{vol_name}' not found. Run 'hologres volume create' first.",
                fmt,
            ))
            return None
        return _build_oss_output_dir(vol["root"], rel_path).rstrip("/")
    # Local file path
    if upload_volume is None:
        print_output(error(
            "INVALID_ARGS",
            f"Local file '{uri}' requires --upload-volume to specify upload destination.",
            fmt,
        ))
        return None
    return _upload_local_file(uri, upload_volume, profile, fmt, net)


def _upload_local_file(
    local_path: str,
    volume_name: str,
    profile: str | None,
    fmt: str,
    net: str = "internet",
) -> str | None:
    """Upload a local file to the specified volume and return the OSS path.

    Returns the OSS path on success, or None on error (error already printed).
    """
    if not os.path.isfile(local_path):
        print_output(error(
            "FILE_NOT_FOUND", f"Local file '{local_path}' not found.", fmt,
        ))
        return None

    vol = _get_volume_config(profile, volume_name)
    if not vol:
        print_output(error(
            "NOT_FOUND",
            f"Volume '{volume_name}' not found. Run 'hologres volume create' first.",
            fmt,
        ))
        return None

    filename = os.path.basename(local_path)
    short_uuid = uuid.uuid4().hex[:8]
    target_file = f"_uploads/{short_uuid}_{filename}"

    try:
        bucket, root_prefix = _get_oss_client(vol, net)
        full_key = root_prefix + target_file
        bucket.put_object_from_file(full_key, local_path)
    except Exception as e:
        print_output(error("OSS_ERROR", f"Failed to upload '{local_path}': {e}", fmt))
        return None

    bucket_name, _ = _parse_oss_root(vol["root"])
    return f"oss://{bucket_name}/{root_prefix}{target_file}"


def _execute_video_gen(
    ctx: click.Context,
    *,
    prompt: str,
    model: str,
    output_dir: str,
    op_name: str,
    img_url: str | None = None,
    video: str | None = None,
    reference_urls: tuple[str, ...] = (),
    parameters_dict: dict | None = None,
    upload_volume: str | None = None,
    net: str = "internet",
) -> None:
    """Shared implementation for video generation subcommands."""
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    # Parse output volume URI
    try:
        volume_name, sub_path = _parse_volume_uri(output_dir)
    except ValueError as e:
        print_output(error("INVALID_ARGS", str(e), fmt))
        return

    volume = _get_volume_config(profile, volume_name)
    if not volume:
        print_output(error(
            "NOT_FOUND",
            f"Volume '{volume_name}' not found. Run 'hologres volume create' first.",
            fmt,
        ))
        return

    # Resolve media URLs
    resolved_img_url: str | None = None
    if img_url:
        resolved_img_url = _resolve_media_url(
            img_url, profile, fmt, upload_volume=upload_volume, net=net,
        )
        if resolved_img_url is None:
            return

    resolved_video: str | None = None
    if video:
        resolved_video = _resolve_media_url(
            video, profile, fmt, upload_volume=upload_volume, net=net,
        )
        if resolved_video is None:
            return

    resolved_refs: list[str] = []
    for ref_uri in reference_urls:
        resolved = _resolve_media_url(
            ref_uri, profile, fmt, upload_volume=upload_volume, net=net,
        )
        if resolved is None:
            return
        resolved_refs.append(resolved)

    try:
        conn = get_connection(profile=profile, read_only=True)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Build JSON request body
        request: dict = {"prompt": prompt}
        if resolved_img_url:
            request["img_url"] = resolved_img_url
        if resolved_video:
            request["video"] = resolved_video
        if resolved_refs:
            request["reference_urls"] = resolved_refs
        if parameters_dict:
            request["parameters"] = parameters_dict

        oss_output_dir = _build_oss_output_dir(volume["root"], sub_path)
        request["output_dir"] = oss_output_dir

        request_json = json_mod.dumps(request, ensure_ascii=False)

        rolearn_literal = volume["rolearn"].replace("'", "''")
        query = f"SELECT ai_gen(%s, %s, to_file(%s, %s, '{rolearn_literal}'))"
        params = (model, request_json, volume["root"], volume["endpoint"])

        rows = conn.execute(query, params)

        duration_ms = (time.time() - start_time) * 1000

        result_text = ""
        if rows:
            first_row = rows[0]
            result_text = list(first_row.values())[0] or ""

        log_operation(
            op_name,
            sql=f"SELECT ai_gen('{model}', '<video-gen-request>')",
            dsn_masked=conn.masked_dsn,
            success=True,
            duration_ms=duration_ms,
        )

        # Parse response JSON
        result_obj = None
        video_oss_path: str | None = None
        task_status: str | None = None
        usage = None
        try:
            result_obj = json_mod.loads(result_text)
            output_obj = result_obj.get("output", {})
            task_status = output_obj.get("task_status")
            video_oss_path = output_obj.get("video_oss_path")
            usage = result_obj.get("usage")
        except (json_mod.JSONDecodeError, TypeError):
            pass

        # Handle task failure
        if task_status == "FAILED" and result_obj:
            fail_output = result_obj.get("output", {})
            fail_msg = fail_output.get("message", "Unknown error")
            fail_code = fail_output.get("code", "QUERY_ERROR")
            print_output(error(
                "QUERY_ERROR",
                f"Video generation failed ({fail_code}): {fail_msg}",
                fmt,
            ))
            return

        if fmt == FORMAT_JSON:
            if video_oss_path:
                data: dict = {
                    "video": {
                        "oss_path": video_oss_path,
                        "volume_path": _oss_to_volume_path(
                            video_oss_path, volume["root"], volume_name,
                        ),
                    },
                }
                if task_status:
                    data["task_status"] = task_status
                if usage:
                    data["usage"] = usage
            else:
                data = {"raw_result": result_text}
            data["model"] = model
            print_output(success(data))
        else:
            if video_oss_path:
                print_output(_oss_to_volume_path(
                    video_oss_path, volume["root"], volume_name,
                ))
            else:
                print_output(result_text)

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            op_name,
            dsn_masked=getattr(conn, "masked_dsn", "unknown") if conn else "unknown",
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Video generation subcommands
# ---------------------------------------------------------------------------

def _build_video_params(
    *,
    resolution: str | None = None,
    ratio: str | None = None,
    duration: int | None = None,
    watermark: str | None = None,
    seed: int | None = None,
    audio_setting: str | None = None,
) -> dict:
    """Build the 'parameters' dict for video gen request body."""
    params: dict = {}
    if resolution is not None:
        params["resolution"] = resolution
    if ratio is not None:
        params["ratio"] = ratio
    if duration is not None:
        params["duration"] = duration
    if watermark is not None:
        params["watermark"] = watermark.lower() == "true"
    if seed is not None:
        params["seed"] = seed
    if audio_setting is not None:
        params["audio_setting"] = audio_setting
    return params


@ai_cmd.command("t2v")
@click.argument("prompt")
@click.option("--output-dir", "-o", required=True,
              help="Output directory. volume://volume_name[/sub_path]")
@click.option("--model", "-m", default="happyhorse-1.0-t2v",
              help="AI model name (default: happyhorse-1.0-t2v)")
@click.option("--resolution", type=click.Choice(["720P", "1080P"], case_sensitive=False),
              default=None, help="Video resolution (default: 1080P)")
@click.option("--ratio", default=None,
              help="Aspect ratio: 16:9 (default), 9:16, 1:1, 4:3, 3:4")
@click.option("--duration", type=int, default=None,
              help="Video duration in seconds, 3-15 (default: 5)")
@click.option("--watermark", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Add watermark (default: true)")
@click.option("--seed", type=int, default=None, help="Random seed [0, 2147483647]")
@click.pass_context
def t2v_cmd(ctx: click.Context, prompt: str, output_dir: str, model: str,
            resolution: str | None, ratio: str | None, duration: int | None,
            watermark: str | None, seed: int | None) -> None:
    """Generate video from text prompt (text-to-video).

    \b
    Examples:
      hologres ai t2v "一只猫在草地上奔跑" -o volume://my_vol/output
      hologres ai t2v "日落" --resolution 720P --ratio 9:16 --duration 10 -o volume://my_vol/output
    """
    params = _build_video_params(
        resolution=resolution, ratio=ratio, duration=duration,
        watermark=watermark, seed=seed,
    )
    _execute_video_gen(
        ctx, prompt=prompt, model=model, output_dir=output_dir,
        op_name="ai.t2v", parameters_dict=params or None,
    )


@ai_cmd.command("i2v")
@click.argument("prompt")
@click.option("--img-url", required=True,
              help="First-frame image URL (volume://vol/path, oss://path, or local file path)")
@click.option("--output-dir", "-o", required=True,
              help="Output directory. volume://volume_name[/sub_path]")
@click.option("--model", "-m", default="happyhorse-1.0-i2v",
              help="AI model name (default: happyhorse-1.0-i2v)")
@click.option("--resolution", type=click.Choice(["720P", "1080P"], case_sensitive=False),
              default=None, help="Video resolution (default: 1080P)")
@click.option("--duration", type=int, default=None,
              help="Video duration in seconds, 3-15 (default: 5)")
@click.option("--watermark", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Add watermark (default: true)")
@click.option("--seed", type=int, default=None, help="Random seed [0, 2147483647]")
@click.option("--upload-volume", default=None,
              help="Volume name for uploading local files (required when using local file paths).")
@click.option("--net", default="internet", type=click.Choice(["internet", "intranet"]),
              help="Network type for file upload: internet (default) or intranet.")
@click.pass_context
def i2v_cmd(ctx: click.Context, prompt: str, img_url: str, output_dir: str,
            model: str, resolution: str | None, duration: int | None,
            watermark: str | None, seed: int | None,
            upload_volume: str | None, net: str) -> None:
    """Generate video from first-frame image (image-to-video).

    \b
    Examples:
      hologres ai i2v "一只猫在草地上奔跑" --img-url volume://my_vol/frame.png -o volume://my_vol/output
      hologres ai i2v "猫" --img-url oss://bucket/frame.png -o volume://my_vol/output
      hologres ai i2v "猫" --img-url ./frame.png --upload-volume my_vol -o volume://my_vol/output
    """
    params = _build_video_params(
        resolution=resolution, duration=duration,
        watermark=watermark, seed=seed,
    )
    _execute_video_gen(
        ctx, prompt=prompt, model=model, output_dir=output_dir,
        op_name="ai.i2v", img_url=img_url, parameters_dict=params or None,
        upload_volume=upload_volume, net=net,
    )


@ai_cmd.command("r2v")
@click.argument("prompt")
@click.option("--reference-url", multiple=True, required=True,
              help="Reference image URL (1-9), volume://vol/path, oss://path, or local file. Repeatable.")
@click.option("--output-dir", "-o", required=True,
              help="Output directory. volume://volume_name[/sub_path]")
@click.option("--model", "-m", default="happyhorse-1.0-r2v",
              help="AI model name (default: happyhorse-1.0-r2v)")
@click.option("--resolution", type=click.Choice(["720P", "1080P"], case_sensitive=False),
              default=None, help="Video resolution (default: 1080P)")
@click.option("--ratio", default=None,
              help="Aspect ratio: 16:9 (default), 9:16, 1:1, 4:3, 3:4")
@click.option("--duration", type=int, default=None,
              help="Video duration in seconds, 3-15 (default: 5)")
@click.option("--watermark", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Add watermark (default: true)")
@click.option("--seed", type=int, default=None, help="Random seed [0, 2147483647]")
@click.option("--upload-volume", default=None,
              help="Volume name for uploading local files (required when using local file paths).")
@click.option("--net", default="internet", type=click.Choice(["internet", "intranet"]),
              help="Network type for file upload: internet (default) or intranet.")
@click.pass_context
def r2v_cmd(ctx: click.Context, prompt: str, reference_url: tuple[str, ...],
            output_dir: str, model: str, resolution: str | None,
            ratio: str | None, duration: int | None,
            watermark: str | None, seed: int | None,
            upload_volume: str | None, net: str) -> None:
    """Generate video from reference images (reference-to-video).

    \b
    Prompt can embed oss:// paths to reference materials. CLI does not
    modify prompt content.

    \b
    Examples:
      hologres ai r2v "女性在花园漫步" --reference-url volume://my_vol/girl.png -o volume://my_vol/output
      hologres ai r2v "人物oss://b/girl.png在跑步" --reference-url oss://b/girl.png -o volume://my_vol/output
      hologres ai r2v "女性漫步" --reference-url ./girl.png --upload-volume my_vol -o volume://my_vol/output
    """
    params = _build_video_params(
        resolution=resolution, ratio=ratio, duration=duration,
        watermark=watermark, seed=seed,
    )
    _execute_video_gen(
        ctx, prompt=prompt, model=model, output_dir=output_dir,
        op_name="ai.r2v", reference_urls=reference_url,
        parameters_dict=params or None,
        upload_volume=upload_volume, net=net,
    )


@ai_cmd.command("video-edit")
@click.argument("prompt")
@click.option("--video", required=True,
              help="Input video URL (volume://vol/path, oss://path, or local file path)")
@click.option("--output-dir", "-o", required=True,
              help="Output directory. volume://volume_name[/sub_path]")
@click.option("--model", "-m", default="happyhorse-1.0-video-edit",
              help="AI model name (default: happyhorse-1.0-video-edit)")
@click.option("--reference-url", multiple=True, default=(),
              help="Reference image URL (0-5), volume://vol/path, oss://path, or local file. Repeatable.")
@click.option("--resolution", type=click.Choice(["720P", "1080P"], case_sensitive=False),
              default=None, help="Video resolution (default: 1080P)")
@click.option("--watermark", type=click.Choice(["true", "false"], case_sensitive=False),
              default=None, help="Add watermark (default: true)")
@click.option("--seed", type=int, default=None, help="Random seed [0, 2147483647]")
@click.option("--audio-setting", type=click.Choice(["auto", "origin"], case_sensitive=False),
              default=None, help="Audio control: auto (default) or origin (keep original)")
@click.option("--upload-volume", default=None,
              help="Volume name for uploading local files (required when using local file paths).")
@click.option("--net", default="internet", type=click.Choice(["internet", "intranet"]),
              help="Network type for file upload: internet (default) or intranet.")
@click.pass_context
def video_edit_cmd(ctx: click.Context, prompt: str, video: str,
                   output_dir: str, model: str,
                   reference_url: tuple[str, ...],
                   resolution: str | None, watermark: str | None,
                   seed: int | None, audio_setting: str | None,
                   upload_volume: str | None, net: str) -> None:
    """Edit video with text instructions (video editing).

    \b
    Examples:
      hologres ai video-edit "转为动漫风格" --video volume://my_vol/input.mp4 -o volume://my_vol/output
      hologres ai video-edit "让人物骑马" --video oss://b/train.mp4 --reference-url volume://my_vol/char.png -o volume://my_vol/out
      hologres ai video-edit "转动漫风" --video ./input.mp4 --upload-volume my_vol -o volume://my_vol/output
    """
    params = _build_video_params(
        resolution=resolution, watermark=watermark,
        seed=seed, audio_setting=audio_setting,
    )
    _execute_video_gen(
        ctx, prompt=prompt, model=model, output_dir=output_dir,
        op_name="ai.video-edit", video=video, reference_urls=reference_url,
        parameters_dict=params or None,
        upload_volume=upload_volume, net=net,
    )


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
@click.option("--reference-url", multiple=True, default=(),
              help="Reference image URL (volume://vol/path, oss://path, or local file). Repeatable.")
@click.option("--upload-volume", default=None,
              help="Volume name for uploading local files (required when using local file paths).")
@click.option("--net", default="internet", type=click.Choice(["internet", "intranet"]),
              help="Network type for file upload: internet (default) or intranet.")
@click.pass_context
def image_gen_cmd(ctx: click.Context, prompt: str, output_dir: str,
                  model: str | None, negative_prompt: str | None,
                  size: str | None, num_images: int | None,
                  prompt_extend: str | None, watermark: str | None,
                  seed: int | None, reference_url: tuple[str, ...],
                  upload_volume: str | None, net: str) -> None:
    """Generate images using Hologres AI function and save to OSS volume.

    \b
    Examples:
      hologres ai image-gen "生成一只可爱的猫" -o volume://my_vol/images
      hologres ai image-gen "生成一只猫" --model qwen-image-2.0 -o volume://my_vol
      hologres ai image-gen "短剧男主" --negative-prompt "低画质" -n 2 -o volume://my_vol/output
      hologres ai image-gen "参照人物风格生成Q版" --reference-url volume://my_vol/ref.png -o volume://my_vol/output
      hologres ai image-gen "生成Q版" --reference-url ./ref.png --upload-volume my_vol -o volume://my_vol/output
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

    # Resolve reference URLs to OSS paths (before DB connection)
    resolved_refs: list[str] = []
    for ref_uri in reference_url:
        resolved = _resolve_media_url(
            ref_uri, profile, fmt, upload_volume=upload_volume, net=net,
        )
        if resolved is None:
            return
        resolved_refs.append(resolved)

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

        if resolved_refs:
            request["reference_urls"] = resolved_refs

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
