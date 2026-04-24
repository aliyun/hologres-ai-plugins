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
    error,
    print_output,
    query_error,
    success,
    success_rows,
)
from .schema import _dump_table_ddl, _list_tables, fetch_table_structure


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
    _list_tables(ctx.obj.get("dsn"), schema_name, ctx.obj.get("format", FORMAT_JSON),
                 operation="table.list")


@table_cmd.command("show")
@click.argument("table")
@click.pass_context
def show_cmd(ctx: click.Context, table: str) -> None:
    """Show table structure: columns, types, nullable, defaults, primary key, comments.

    TABLE: 'table_name' or 'schema.table_name'.
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if "." in table:
        schema_name, table_name = table.rsplit(".", 1)
    else:
        schema_name, table_name = "public", table

    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        result = fetch_table_structure(conn, schema_name, table_name)

        if result is None:
            print_output(error("TABLE_NOT_FOUND", f"Table '{schema_name}.{table_name}' not found", fmt))
            return

        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.show", sql=f"SHOW {schema_name}.{table_name}",
                      dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(result["columns"]), duration_ms=duration_ms)

        if fmt == FORMAT_JSON:
            print_output(success(result))
        else:
            print_output(success_rows(result["columns"], fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.show", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
