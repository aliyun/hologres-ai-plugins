"""Table management commands for Hologres CLI."""

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
from .schema import _dump_table_ddl


@click.group("table")
def table_cmd() -> None:
    """Table management commands."""
    pass


@table_cmd.command("dump")
@click.argument("table")
@click.pass_context
def dump_cmd(ctx: click.Context, table: str) -> None:
    """Export DDL for a table using hg_dump_script().

    TABLE should be in format 'schema_name.table_name'.

    \b
    Examples:
      hologres table dump public.my_table
      hologres table dump myschema.orders
    """
    _dump_table_ddl(ctx.obj.get("dsn"), table, ctx.obj.get("format", FORMAT_JSON),
                    operation="table.dump")


@table_cmd.command("list")
@click.option("--schema", "-s", "schema_name", default=None, help="Filter by schema name")
@click.pass_context
def list_cmd(ctx: click.Context, schema_name: Optional[str]) -> None:
    """List all tables in the database (excluding system schemas)."""
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = """
        SELECT schemaname AS schema, tablename AS table_name, tableowner AS owner
        FROM pg_catalog.pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hg_internal')
    """
    params = []
    if schema_name:
        sql += " AND schemaname = %s"
        params.append(schema_name)
    sql += " ORDER BY schemaname, tablename"

    try:
        rows = conn.execute(sql, tuple(params) if params else None)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.list", sql=sql, dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.list", sql=sql, dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
