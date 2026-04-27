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
    error,
    print_output,
    query_error,
    success,
    success_rows,
)
from .schema import _validate_identifier

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


@view_cmd.command("show")
@click.argument("view")
@click.pass_context
def show_cmd(ctx: click.Context, view: str) -> None:
    """Show view structure: definition, columns, types, nullable, defaults, comments.

    VIEW: 'view_name' or 'schema.view_name'.
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    # Parse schema.view format
    if "." in view:
        schema_name, view_name = view.rsplit(".", 1)
    else:
        schema_name, view_name = "public", view

    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(view_name, "view name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Query view definition and owner
        view_sql = """
            SELECT definition, viewowner
            FROM pg_catalog.pg_views
            WHERE schemaname = %s AND viewname = %s
        """
        view_rows = conn.execute(view_sql, (schema_name, view_name))

        if not view_rows:
            print_output(error("VIEW_NOT_FOUND",
                               f"View '{schema_name}.{view_name}' not found", fmt))
            return

        definition = view_rows[0]["definition"]
        owner = view_rows[0]["viewowner"]

        # Query column info with comments
        # NOTE: Views are not in pg_statio_all_tables, so we use pg_class + pg_namespace
        # to get the relid for joining with pg_description
        columns_sql = """
            SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                   c.ordinal_position, COALESCE(pd.description, '') AS comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_class cls
                ON cls.relname = c.table_name
            LEFT JOIN pg_catalog.pg_namespace ns
                ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
            LEFT JOIN pg_catalog.pg_description pd
                ON cls.oid = pd.objoid AND c.ordinal_position = pd.objsubid
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
        """
        columns = conn.execute(columns_sql, (schema_name, view_name))

        result = {
            "schema": schema_name,
            "view": view_name,
            "owner": owner,
            "definition": definition,
            "columns": columns,
        }

        duration_ms = (time.time() - start_time) * 1000
        log_operation("view.show", sql=f"SHOW {schema_name}.{view_name}",
                      dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(columns), duration_ms=duration_ms)

        if fmt == FORMAT_JSON:
            print_output(success(result))
        else:
            print_output(success_rows(columns, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("view.show", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
