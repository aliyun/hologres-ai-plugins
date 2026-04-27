"""GUC parameter management commands for Hologres CLI."""

from __future__ import annotations

import time

import click
from psycopg import sql as psql

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    error,
    print_output,
    query_error,
    success,
)
from .schema import _validate_identifier


@click.group("guc")
def guc_cmd() -> None:
    """GUC parameter management commands."""
    pass


@guc_cmd.command("show")
@click.argument("param_name")
@click.pass_context
def show_cmd(ctx: click.Context, param_name: str) -> None:
    """Show the current value of a GUC parameter.

    PARAM_NAME: GUC parameter name (e.g., optimizer_join_order).
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        _validate_identifier(param_name, "GUC parameter name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # SHOW treats param name as identifier, not a parameterized value
        show_sql = psql.SQL("SHOW {}").format(psql.Identifier(param_name))
        rows = conn.execute(show_sql.as_string(conn.conn))

        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.show", sql=show_sql.as_string(conn.conn),
                      dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms)

        value = rows[0][list(rows[0].keys())[0]] if rows else None
        print_output(success({"param": param_name, "value": value}))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.show", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@guc_cmd.command("set")
@click.argument("param_name")
@click.argument("value")
@click.pass_context
def set_cmd(ctx: click.Context, param_name: str, value: str) -> None:
    """Set a GUC parameter at the database level (persistent).

    This executes ALTER DATABASE to set the parameter, which persists
    across sessions and applies to all new connections to the database.

    \b
    Examples:
      hologres guc set optimizer_join_order query
      hologres guc set statement_timeout '5min'

    \b
    PARAM_NAME: GUC parameter name (e.g., optimizer_join_order).
    VALUE: Parameter value (e.g., 'query' or 'on').
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        _validate_identifier(param_name, "GUC parameter name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        dbname = conn.database
        # ALTER DATABASE <dbname> SET <param> = <value>
        # dbname and param_name are identifiers (need quoting)
        # value is a literal — DDL does not support parameterized placeholders,
        # so use psycopg.sql.Literal for safe escaping
        alter_sql = psql.SQL("ALTER DATABASE {} SET {} = {}").format(
            psql.Identifier(dbname),
            psql.Identifier(param_name),
            psql.Literal(value),
        )
        final_sql = alter_sql.as_string(conn.conn)
        conn.execute(final_sql)

        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.set", sql=final_sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)

        if fmt == FORMAT_JSON:
            print_output(success({
                "param": param_name,
                "value": value,
                "scope": "database",
                "database": dbname,
            }))
        else:
            print_output(
                f"GUC parameter '{param_name}' set to '{value}' "
                f"at database level (database: {dbname}). "
                f"Change takes effect for new sessions."
            )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.set", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
