"""Model management commands for Hologres CLI."""

from __future__ import annotations

import re
import time

import click

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    error,
    print_output,
    query_error,
    success,
    success_rows,
)

_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


@click.group("model")
def model_cmd() -> None:
    """AI model management commands."""
    pass


@model_cmd.command("list")
@click.option("--task", "-t", default=None, help="Filter by task type (e.g. embedding, video-generation)")
@click.option("--model-type", default=None, help="Filter by model type (e.g. qwen3-vl-embedding)")
@click.option("--search", default=None,
              help="Substring match on model_name OR model_type (case-insensitive)")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    task: str | None,
    model_type: str | None,
    search: str | None,
) -> None:
    """List registered external AI models.

    \b
    Examples:
      hologres model list
      hologres model list --task embedding
      hologres model list --model-type qwen3-vl-embedding
      hologres model list --search happy
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
        if search:
            needle = search.lower()
            rows = [
                r for r in rows
                if needle in (r.get("model_name") or "").lower()
                or needle in (r.get("model_type") or "").lower()
            ]

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


@model_cmd.command("catalog")
@click.pass_context
def catalog_cmd(ctx: click.Context) -> None:
    """List supported AI model types (not supported now)."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    print_output(error("NOT_SUPPORTED", "model catalog is not supported now", fmt))


@model_cmd.command("delete")
@click.argument("model_name")
@click.option(
    "--confirm",
    is_flag=True,
    default=False,
    help="[REQUIRED to execute] Confirm the delete operation. "
         "Without --confirm, only a dry-run preview is shown (safety).",
)
@click.pass_context
def delete_cmd(ctx: click.Context, model_name: str, confirm: bool) -> None:
    """Delete a registered external AI model.

    \b
    MODEL_NAME: Name of the registered model (see `hologres model list`).

    \b
    SAFETY: Destructive operation. Defaults to dry-run; use --confirm to execute.

    \b
    Examples:
      hologres model delete embed11               # dry-run preview
      hologres model delete embed11 --confirm     # actually deletes
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    profile = ctx.obj.get("profile")

    if not _MODEL_NAME_RE.match(model_name):
        print_output(error(
            "INVALID_INPUT",
            "model_name may only contain letters, digits, underscore (_), "
            "hyphen (-), and dot (.)",
            fmt,
        ))
        return

    delete_sql = f"CALL delete_external_model('{model_name}')"

    if not confirm:
        print_output(success(
            {"model": model_name, "dry_run": True},
            fmt,
            message=f"Dry-run: model '{model_name}' was NOT deleted. "
                    f"Re-run with --confirm to execute.",
        ))
        return

    start_time = time.time()
    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        conn.execute(delete_sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.delete",
            sql=delete_sql,
            dsn_masked=conn.masked_dsn,
            success=True,
            duration_ms=duration_ms,
        )
        if fmt == FORMAT_JSON:
            print_output(success(
                {"model": model_name, "deleted": True},
                fmt,
                message=f"Model '{model_name}' deleted successfully",
            ))
        else:
            print_output(f"Model '{model_name}' deleted successfully")
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.delete",
            sql=delete_sql,
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@model_cmd.command("create")
@click.pass_context
def create_cmd(ctx: click.Context) -> None:
    """Register an external AI model (not supported now)."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    print_output(error("NOT_SUPPORTED", "model create is not supported now", fmt))
