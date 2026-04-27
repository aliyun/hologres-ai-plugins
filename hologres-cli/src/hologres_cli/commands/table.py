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
from .schema import _dump_table_ddl, _get_table_size, _list_tables, _validate_identifier, fetch_table_structure


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
    _dump_table_ddl(ctx.obj.get("profile"), table, ctx.obj.get("format", FORMAT_JSON),
                    operation="table.dump")


@table_cmd.command("list")
@click.option("--schema", "-s", "schema_name", default=None, help="Filter by schema name")
@click.pass_context
def list_cmd(ctx: click.Context, schema_name: Optional[str]) -> None:
    """List all tables in the database (excluding system schemas)."""
    _list_tables(ctx.obj.get("profile"), schema_name, ctx.obj.get("format", FORMAT_JSON),
                 operation="table.list")


@table_cmd.command("show")
@click.argument("table")
@click.pass_context
def show_cmd(ctx: click.Context, table: str) -> None:
    """Show table structure: columns, types, nullable, defaults, primary key, comments.

    TABLE: 'table_name' or 'schema.table_name'.
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if "." in table:
        schema_name, table_name = table.rsplit(".", 1)
    else:
        schema_name, table_name = "public", table

    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
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


@table_cmd.command("size")
@click.argument("table")
@click.pass_context
def size_cmd(ctx: click.Context, table: str) -> None:
    """Get storage size of a table.

    TABLE should be in format 'schema_name.table_name'.

    \b
    Examples:
      hologres table size public.my_table
      hologres table size myschema.orders
    """
    _get_table_size(ctx.obj.get("profile"), table, ctx.obj.get("format", FORMAT_JSON),
                    operation="table.size")


@table_cmd.command("drop")
@click.argument("table")
@click.option("--if-exists", is_flag=True, default=False,
              help="Add IF EXISTS clause. No error if table does not exist.")
@click.option("--cascade", is_flag=True, default=False,
              help="Add CASCADE clause to drop dependent objects too.")
@click.option("--confirm", is_flag=True, default=False,
              help="[REQUIRED to execute] Confirm the drop operation. "
                   "Without --confirm, only dry-run SQL is shown (safety).")
@click.pass_context
def drop_cmd(ctx: click.Context, table: str, if_exists: bool, cascade: bool, confirm: bool) -> None:
    """Drop a table from the database.

    TABLE: Table name in format [schema.]table_name.

    SAFETY: Destructive operation. By default only shows the SQL.
    Use --confirm to actually execute the DROP.

    \b
    Examples:
      hologres table drop my_table              # dry-run, shows SQL
      hologres table drop my_table --confirm    # actually drops
      hologres table drop my_table --if-exists --confirm
      hologres table drop my_table --cascade --confirm
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Parse schema.table format
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

    # Build SQL
    exists_clause = " IF EXISTS" if if_exists else ""
    cascade_clause = " CASCADE" if cascade else ""
    sql = f"DROP TABLE{exists_clause} {schema_name}.{table_name}{cascade_clause}"

    # Dry-run mode
    if not confirm:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode)"))
        return

    # Execute mode
    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.drop", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Statement executed successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.drop", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@table_cmd.command("truncate")
@click.argument("table")
@click.option("--confirm", is_flag=True, default=False,
              help="[REQUIRED to execute] Confirm the truncate operation. "
                   "Without --confirm, only dry-run SQL is shown (safety).")
@click.pass_context
def truncate_cmd(ctx: click.Context, table: str, confirm: bool) -> None:
    """Truncate (empty) a table.

    TABLE: Table name in format [schema.]table_name.

    SAFETY: Destructive operation. By default only shows the SQL.
    Use --confirm to actually execute the TRUNCATE.

    \b
    Examples:
      hologres table truncate my_table              # dry-run, shows SQL
      hologres table truncate my_table --confirm    # actually truncates
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Parse schema.table format
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

    # Build SQL
    sql = f"TRUNCATE TABLE {schema_name}.{table_name}"

    # Dry-run mode
    if not confirm:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode)"))
        return

    # Execute mode
    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.truncate", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Statement executed successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.truncate", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@table_cmd.command("properties")
@click.argument("table")
@click.pass_context
def properties_cmd(ctx: click.Context, table: str) -> None:
    """Show Hologres-specific table properties (orientation, distribution_key, etc.).

    TABLE: 'table_name' or 'schema.table_name'.

    \b
    Examples:
      hologres table properties public.my_table
      hologres table properties myschema.orders
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Parse schema.table format
        if "." in table:
            schema_name, table_name = table.rsplit(".", 1)
        else:
            schema_name, table_name = "public", table

        # Validate identifiers
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")

        # NOTE: 实际列名可能与需求示例不同，若查询失败需确认
        # hologres.hg_table_properties 的实际列名
        properties_sql = """
            SELECT property_key, property_value
            FROM hologres.hg_table_properties
            WHERE table_namespace = %s AND table_name = %s
            ORDER BY property_key
        """
        rows = conn.execute(properties_sql, (schema_name, table_name))

        if not rows:
            print_output(error("TABLE_NOT_FOUND",
                               f"Table '{schema_name}.{table_name}' not found or has no properties",
                               fmt))
            return

        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.properties", sql=properties_sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.properties", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.properties", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
