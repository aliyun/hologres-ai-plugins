"""Model management commands for Hologres CLI."""

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
    success_rows,
)


@click.group("model")
def model_cmd() -> None:
    """AI model management commands."""
    pass


@model_cmd.command("list")
@click.option("--task", "-t", default=None, help="Filter by task type (e.g. embedding, video-generation)")
@click.option("--model-type", default=None, help="Filter by model type (e.g. qwen3-vl-embedding)")
@click.pass_context
def list_cmd(ctx: click.Context, task: str | None, model_type: str | None) -> None:
    """List registered external AI models.

    \b
    Examples:
      hologres model list
      hologres model list --task embedding
      hologres model list --model-type qwen3-vl-embedding
      hologres -f table model list
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
        query = "SELECT model_name, model_type, model_provider, task FROM list_external_models()"
        rows = conn.execute(query)

        # Client-side filtering (list_external_models() does not support WHERE)
        if task:
            rows = [r for r in rows if r.get("task") == task]
        if model_type:
            rows = [r for r in rows if r.get("model_type") == model_type]

        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.list",
            sql=query,
            dsn_masked=conn.masked_dsn,
            success=True,
            row_count=len(rows),
            duration_ms=duration_ms,
        )
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.list",
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
