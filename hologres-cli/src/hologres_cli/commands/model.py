"""Model management commands for Hologres CLI."""

from __future__ import annotations

import json
import re
import time
from importlib.resources import files

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


def _load_catalog() -> dict:
    """Load the bundled model catalog from models.json.

    Uses importlib.resources so it works in both source checkouts and
    zip-installed wheels.
    """
    raw = files("hologres_cli.commands").joinpath("models.json").read_text(encoding="utf-8")
    return json.loads(raw)


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


@model_cmd.command("catalog")
@click.option("--task", "-t", default=None, help="Filter by task type (e.g. embedding, video-generation)")
@click.pass_context
def catalog_cmd(ctx: click.Context, task: str | None) -> None:
    """List supported AI model types from the bundled catalog (models.json).

    \b
    Examples:
      hologres model catalog
      hologres model catalog --task embedding
      hologres -f table model catalog
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    try:
        data = _load_catalog()
    except Exception as e:
        print_output(error("INTERNAL_ERROR", f"Failed to load model catalog: {e}", fmt))
        return

    rows = [
        {"model_type": k, "model_provider": v.get("provider"), "task": v.get("task")}
        for k, v in data.items()
    ]
    if task:
        rows = [r for r in rows if r["task"] == task]

    print_output(success_rows(rows, fmt))


@model_cmd.command("delete")
@click.argument("model_name")
@click.option(
    "--confirm",
    is_flag=True,
    default=False,
    help="[REQUIRED to execute] Confirm the delete operation. "
         "Without --confirm, only dry-run SQL is shown (safety).",
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
      hologres model delete embed11               # dry-run, shows SQL
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

    sql = f"CALL delete_external_model('{model_name}')"

    if not confirm:
        # MR review feedback: do not expose the underlying SQL in dry-run output.
        # delete_external_model is a fixed CALL whose only variable is model_name,
        # so showing it adds no value and leaks an internal stored-proc detail.
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
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.delete",
            sql=sql,
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
            sql=sql,
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=str(e),
            duration_ms=duration_ms,
        )
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
