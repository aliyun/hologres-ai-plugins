"""Partition management commands for Hologres CLI."""

from __future__ import annotations

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
    success_rows,
)
from .schema import _validate_identifier


@click.group("partition")
def partition_cmd() -> None:
    """Partition management commands."""
    pass


def _is_logical_partitioned(conn, schema_name: str, table_name: str) -> bool:
    """Check if table is a logical partitioned table."""
    sql = """
        SELECT property_value
        FROM hologres.hg_table_properties
        WHERE table_namespace = %s
          AND table_name = %s
          AND property_key = 'is_logical_partitioned_table'
          AND property_value = 'true'
    """
    rows = conn.execute(sql, (schema_name, table_name))
    return len(rows) > 0


def _table_exists(conn, schema_name: str, table_name: str) -> bool:
    """Check if table exists."""
    sql = """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
    """
    rows = conn.execute(sql, (schema_name, table_name))
    return len(rows) > 0


@partition_cmd.command("list")
@click.argument("table")
@click.pass_context
def list_cmd(ctx: click.Context, table: str) -> None:
    """List partitions of a logical partition table.

    TABLE: 'table_name' or 'schema.table_name'.

    \b
    Examples:
      hologres partition list my_table
      hologres partition list public.logs
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Parse schema.table
    if "." in table:
        schema_name, table_name = table.rsplit(".", 1)
    else:
        schema_name, table_name = "public", table

    # Validate identifiers
    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        # 1. Check table exists
        if not _table_exists(conn, schema_name, table_name):
            print_output(error("TABLE_NOT_FOUND",
                f"Table '{schema_name}.{table_name}' not found", fmt))
            return

        # 2. Check is logical partition table
        if not _is_logical_partitioned(conn, schema_name, table_name):
            print_output(error("NOT_LOGICAL_PARTITION",
                f"Table '{schema_name}.{table_name}' is not a logical partition table. "
                "Only logical partition tables are supported.", fmt))
            return

        # 3. Query partition list using Hologres built-in function
        partition_sql = (
            "SELECT * FROM hologres.hg_list_logical_partition"
            f"('{schema_name}.{table_name}')"
        )
        rows = conn.execute(partition_sql)

        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.list", sql=partition_sql,
                      dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms)

        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.list", dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
