"""Extension management commands for Hologres CLI."""

from __future__ import annotations

import time

import click
from psycopg import sql

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
from .schema import _validate_identifier


@click.group("extension")
def extension_cmd() -> None:
    """Extension management commands."""
    pass


@extension_cmd.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List installed extensions in the database."""
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        query = """
            SELECT extname AS name, extversion AS version,
                   n.nspname AS schema
            FROM pg_extension e
            JOIN pg_namespace n ON e.extnamespace = n.oid
            ORDER BY extname
        """
        rows = conn.execute(query)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("extension.list", sql=query, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("extension.list", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@extension_cmd.command("create")
@click.argument("name")
@click.option("--if-not-exists", is_flag=True, help="Do not error if extension already exists")
@click.pass_context
def create_cmd(ctx: click.Context, name: str, if_not_exists: bool) -> None:
    """Create (install) a database extension.

    \b
    Common extensions:
      flow_analysis, roaring_bitmap, postgis, hstore, hologres_fdw

    \b
    Examples:
      hologres extension create roaring_bitmap
      hologres extension create postgis --if-not-exists
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Validate extension name
    try:
        _validate_identifier(name, "extension name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    # Build SQL using psycopg.sql for safe identifier escaping
    # CREATE EXTENSION [IF NOT EXISTS] name
    parts = [sql.SQL("CREATE EXTENSION")]
    if if_not_exists:
        parts.append(sql.SQL(" IF NOT EXISTS"))
    parts.append(sql.SQL(" "))
    parts.append(sql.Identifier(name))

    create_sql_obj = sql.Composed(parts)

    # Execute the CREATE EXTENSION
    start_time = time.time()
    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        create_sql = create_sql_obj.as_string(conn.conn)
        conn.execute(create_sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("extension.create", sql=create_sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        if fmt == FORMAT_JSON:
            print_output(success({"extension": name, "created": True}))
        else:
            print_output(f"Extension '{name}' created successfully")
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("extension.create", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("extension.create", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
