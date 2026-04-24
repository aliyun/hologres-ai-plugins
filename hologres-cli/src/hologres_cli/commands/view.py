"""View management commands for Hologres CLI."""

from __future__ import annotations

import time
from typing import Optional

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

@click.group("view")
def view_cmd() -> None:
    """View management commands."""
    pass


@view_cmd.command("list")
@click.option("--schema", "-s", "schema_name", default=None, help="Filter by schema name")
@click.pass_context
def list_cmd(ctx: click.Context, schema_name: Optional[str]) -> None:
    """List all views in the database (excluding system schemas)."""
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = """
        SELECT schemaname AS schema, viewname AS view_name, viewowner AS owner
        FROM pg_catalog.pg_views
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hg_internal')
    """
    params: list = []
    if schema_name:
        sql += " AND schemaname = %s"
        params.append(schema_name)
    sql += " ORDER BY schemaname, viewname"

    try:
        rows = conn.execute(sql, tuple(params))
        duration_ms = (time.time() - start_time) * 1000
        log_operation("view.list", sql=sql, dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("view.list", sql=sql, dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
