"""Model management commands for Hologres CLI."""

from __future__ import annotations

import json
import re
import time
from importlib.resources import files

import click
from psycopg import sql

from ..config_store import ConfigError, get_current_profile, get_profile
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
    success_rows,
)

_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
REGION_PATTERN = re.compile(r"^[a-z0-9-]+$")

# Regions where the dashscope VPC host requires a '-prd' suffix
# (e.g. vpc-cn-hangzhou-prd.dashscope.aliyuncs.com).
# Only applies to model_url; function_server_url is unaffected.
_REGIONS_WITH_PRD_SUFFIX = frozenset({"cn-hangzhou", "ap-southeast-1"})


@click.group("model")
def model_cmd() -> None:
    """AI model management commands."""
    pass


def _load_catalog() -> dict:
    """Load the bundled model catalog from models.json.

    Uses importlib.resources so it works in both source checkouts and
    zip-installed wheels.
    """
    raw = files("hologres_cli.commands").joinpath(
        "models.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _resolve_region(profile_name: str | None) -> str:
    """Read region_id from current/named profile. No CLI override."""
    profile = get_profile(
        profile_name) if profile_name else get_current_profile()
    region = profile.get("region_id")
    if not region:
        raise ValueError(
            "region_id is not set in current profile; run `hologres config` first"
        )
    if not REGION_PATTERN.match(region):
        raise ValueError(
            f"region_id '{region}' contains invalid characters; "
            f"expected lowercase letters, digits, or hyphens only"
        )
    return region


def _build_endpoint(entry: dict, region: str) -> str:
    """Combine function_server_url + /providers/{provider} + ?url={model_url}.

    function_server_url in models.json is host:port only (no path),
    e.g. 'http://model-server-{region}.api.aliyun-inc.com:8000'.

    For dashscope VPC endpoints in 'cn-hangzhou' / 'ap-southeast-1', the
    model_url host requires a '-prd' suffix (e.g.
    vpc-cn-hangzhou-prd.dashscope.aliyuncs.com). function_server_url is
    unaffected.
    """
    fsu = entry["function_server_url"].replace("{region}", region)
    provider = entry["provider"]
    model_url_region = (
        f"{region}-prd" if region in _REGIONS_WITH_PRD_SUFFIX else region
    )
    model_url = entry["model_url"].replace("{region}", model_url_region)
    return f"{fsu}/providers/{provider}?url={model_url}"


def _mask_api_key(rendered_sql: str, api_key: str) -> str:
    """Replace api_key occurrences in a rendered SQL string with '****'."""
    return rendered_sql.replace(f"'{api_key}'", "'****'")


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
@click.option("--task", "-t", default=None, help="Filter by task type (e.g. embedding, video-generation)")
@click.option("--search", default=None, help="Substring match on model_type (case-insensitive)")
@click.pass_context
def catalog_cmd(ctx: click.Context, task: str | None, search: str | None) -> None:
    """List supported AI model types from the bundled catalog (models.json).

    \b
    Examples:
      hologres model catalog
      hologres model catalog --task embedding
      hologres model catalog --search happy
      hologres -f table model catalog
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    try:
        data = _load_catalog()
    except Exception as e:
        print_output(
            error("INTERNAL_ERROR", f"Failed to load model catalog: {e}", fmt))
        return

    rows = [
        {"model_type": k, "model_provider": v.get(
            "provider"), "task": v.get("task")}
        for k, v in data.items()
    ]
    if task:
        rows = [r for r in rows if r["task"] == task]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in (r["model_type"] or "").lower()]

    print_output(success_rows(rows, fmt))


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
        # MR review feedback: do not expose the underlying SQL in dry-run output.
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
@click.option("--name", "-n", "name", required=True,
              help="Model name to register in Hologres")
@click.option("--type", "-t", "model_type", required=True,
              help="Model type from the bundled catalog (see `hologres model catalog`)")
@click.option("--api-key", "api_key", required=True,
              help="Provider API key (never written to logs or shown in output)")
@click.option("--config", "config_json", default="{}", show_default=True,
              help="Extra JSON config string")
@click.option("--dry-run", is_flag=True,
              help="Show what would be registered without executing")
@click.pass_context
def create_cmd(
    ctx: click.Context,
    name: str,
    model_type: str,
    api_key: str,
    config_json: str,
    dry_run: bool,
) -> None:
    """Register an external AI model.

    \b
    Examples:
      hologres model create --name my_chat --type qwen3-max --api-key sk-xxx
      hologres model create -n my_embed -t text-embedding-v3 --api-key sk-xxx
      hologres model create -n my_chat -t qwen3-max --api-key sk-xxx --dry-run
    """
    profile_name = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # 1. Validate --config is well-formed JSON (passed as a string into SQL).
    try:
        json.loads(config_json)
    except json.JSONDecodeError as e:
        print_output(
            error("INVALID_INPUT", f"--config must be valid JSON: {e}", fmt))
        return

    # 2. Look up model_type in the bundled catalog.
    try:
        catalog = _load_catalog()
    except Exception as e:
        print_output(
            error("INTERNAL_ERROR", f"Failed to load model catalog: {e}", fmt))
        return
    if model_type not in catalog:
        print_output(error(
            "MODEL_TYPE_NOT_SUPPORTED",
            f"model_type '{model_type}' not found. "
            f"Use `hologres model catalog` to see supported types.",
            fmt,
        ))
        return
    entry = catalog[model_type]
    provider = entry["provider"]
    task = entry["task"]

    # 3. Resolve region strictly from the profile (no CLI override per review feedback).
    try:
        region = _resolve_region(profile_name)
    except (ValueError, ConfigError) as e:
        print_output(error("INVALID_ARGS", str(e), fmt))
        return

    endpoint = _build_endpoint(entry, region)

    # 4. Build the CALL with psycopg.sql.Literal — every literal is properly quoted,
    # blocking SQL injection on user-supplied --name / --config / api_key etc.
    call_sql = sql.SQL(
        "CALL add_external_model({name}, {mtype}, {prov}, {ep}, {key}, {task}, {cfg})"
    ).format(
        name=sql.Literal(name),
        mtype=sql.Literal(model_type),
        prov=sql.Literal(provider),
        ep=sql.Literal(endpoint),
        key=sql.Literal(api_key),
        task=sql.Literal(task),
        cfg=sql.Literal(config_json),
    )

    # 5. Dry-run: report what would be registered, do NOT execute.
    # MR review feedback: do not expose the underlying SQL in dry-run output —
    # the api_key risk and the leaked endpoint/task internals are both
    # better kept inside the process.
    if dry_run:
        print_output(success(
            {"model_name": name, "model_type": model_type, "dry_run": True},
            fmt,
            message=f"Dry-run: model '{name}' was NOT registered. "
                    f"Re-run without --dry-run to execute.",
        ))
        return

    # 6. Execute against the live database.
    try:
        conn = get_connection(profile=profile_name, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        executable_sql = call_sql.as_string(conn.conn)
        masked_for_log = _mask_api_key(executable_sql, api_key)
        conn.execute(executable_sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation(
            "model.create",
            sql=masked_for_log,
            dsn_masked=conn.masked_dsn,
            success=True,
            duration_ms=duration_ms,
        )
        print_output(success(
            {
                "model_name": name,
                "model_type": model_type,
                "created": True,
            },
            fmt,
            message=f"Model '{name}' registered successfully",
        ))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        # Defensive: mask api_key in the error message in case the backend echoes it.
        err_msg = _mask_api_key(str(e), api_key)
        log_operation(
            "model.create",
            dsn_masked=conn.masked_dsn,
            success=False,
            error_code="QUERY_ERROR",
            error_message=err_msg,
            duration_ms=duration_ms,
        )
        print_output(query_error(err_msg, fmt))
    finally:
        conn.close()
