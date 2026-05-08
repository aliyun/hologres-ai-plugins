"""AI commands for Hologres CLI."""

from __future__ import annotations

import json as json_mod
import os
import time
import urllib.parse
import urllib.request

import click

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    print_output,
    query_error,
    success,
)


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
@click.option("--download-dir", "-d", required=True, help="Directory to save downloaded images (required)")
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
def image_gen_cmd(ctx: click.Context, prompt: str, download_dir: str,
                  model: str | None, negative_prompt: str | None,
                  size: str | None, num_images: int | None,
                  prompt_extend: str | None, watermark: str | None,
                  seed: int | None) -> None:
    """Generate images using Hologres AI function.

    \b
    Examples:
      hologres ai image-gen "生成一只可爱的猫" -d ./images
      hologres ai image-gen "生成一只猫" --model qwen-image-2.0 -d /tmp/images
      hologres ai image-gen "短剧男主" --negative-prompt "低画质" -n 2 -d ./output
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

        request_json = json_mod.dumps(request, ensure_ascii=False)

        if model:
            query = "SELECT ai_gen(%s, %s)"
            params = (model, request_json)
        else:
            query = "SELECT ai_gen(%s)"
            params = (request_json,)

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

        # Parse response JSON, extract image_urls and usage
        image_urls: list = []
        usage = None
        try:
            result_obj = json_mod.loads(result_text)
            image_urls = result_obj.get("image_urls", [])
            usage = result_obj.get("usage")
        except (json_mod.JSONDecodeError, TypeError):
            pass

        if image_urls:
            # Download images to local directory
            os.makedirs(download_dir, exist_ok=True)
            local_paths: list = []
            errors: list = []
            for i, url in enumerate(image_urls, 1):
                parsed = urllib.parse.urlparse(url)
                filename = os.path.basename(parsed.path)
                if not filename:
                    filename = f"image_{i}.png"
                filepath = os.path.join(download_dir, filename)
                try:
                    urllib.request.urlretrieve(url, filepath)
                    local_paths.append(filepath)
                except Exception as dl_err:
                    local_paths.append(None)
                    errors.append({"index": i, "url": url, "error": str(dl_err)})

        if fmt == FORMAT_JSON:
            if image_urls:
                data: dict = {"images": local_paths}
                if usage:
                    data["usage"] = usage
                if errors:
                    data["errors"] = errors
            else:
                data = {"raw_result": result_text}
            if model:
                data["model"] = model
            print_output(success(data))
        else:
            if image_urls:
                print_output("\n".join(p or "DOWNLOAD_FAILED" for p in local_paths))
            else:
                print_output(result_text)

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "ai.image-gen",
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
