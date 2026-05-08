"""AI commands for Hologres CLI."""

from __future__ import annotations

import time

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
