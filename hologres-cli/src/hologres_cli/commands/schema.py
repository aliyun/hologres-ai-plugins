"""Schema inspection commands for Hologres CLI."""

from __future__ import annotations

import re
import time
from typing import Optional

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

# Validate schema/table names to allow only alphanumeric, underscore, and hyphen
SAFE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')


def _validate_identifier(name: str, label: str = "identifier") -> None:
    """Validate that a database identifier is safe (prevents SQL injection)."""
    if not SAFE_NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label} '{name}': only letters, digits, underscores, and hyphens allowed"
        )


@click.group("schema")
def schema_cmd() -> None:
    """Schema inspection commands."""
    pass


@schema_cmd.command("tables")
@click.option("--schema", "-s", "schema_name", default=None, help="Filter by schema name")
@click.pass_context
def tables_cmd(ctx: click.Context, schema_name: Optional[str]) -> None:
    """List all tables in the database."""
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
        log_operation("schema.tables", sql=sql, dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.tables", sql=sql, dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@schema_cmd.command("describe")
@click.argument("table")
@click.pass_context
def describe_cmd(ctx: click.Context, table: str) -> None:
    """Describe a table's structure. TABLE: 'table_name' or 'schema.table_name'."""
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
        columns_sql = """
            SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                   c.ordinal_position, COALESCE(pd.description, '') AS comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_statio_all_tables st
                ON c.table_schema = st.schemaname AND c.table_name = st.relname
            LEFT JOIN pg_catalog.pg_description pd
                ON st.relid = pd.objoid AND c.ordinal_position = pd.objsubid
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
        """
        columns = conn.execute(columns_sql, (schema_name, table_name))

        if not columns:
            print_output(error("TABLE_NOT_FOUND", f"Table '{schema_name}.{table_name}' not found", fmt))
            return

        pk_sql = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = %s AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
        """
        pk_columns = [r["column_name"] for r in conn.execute(pk_sql, (schema_name, table_name))]

        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.describe", sql=f"DESCRIBE {schema_name}.{table_name}",
                      dsn_masked=conn.masked_dsn, success=True, row_count=len(columns), duration_ms=duration_ms)

        result = {
            "schema": schema_name, "table": table_name,
            "primary_key": pk_columns, "columns": columns,
        }

        if fmt == FORMAT_JSON:
            print_output(success(result))
        else:
            print_output(success_rows(columns, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.describe", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@schema_cmd.command("dump")
@click.argument("table")
@click.pass_context
def dump_cmd(ctx: click.Context, table: str) -> None:
    """Export DDL for a table using hg_dump_script().

    TABLE should be in format 'schema_name.table_name'.

    \b
    Examples:
      hologres schema dump public.my_table
      hologres schema dump myschema.orders
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Parse schema.table format
        if "." in table:
            schema_name, table_name = table.rsplit(".", 1)
        else:
            schema_name, table_name = "public", table

        # Validate identifiers to prevent SQL injection
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")

        # Use psycopg.sql.Identifier for safe identifier escaping
        query = sql.SQL("SELECT hg_dump_script({})").format(
            sql.Identifier(schema_name, table_name)
        )
        dump_sql = query.as_string(conn.conn)
        result = conn.execute(dump_sql)

        if not result or not result[0]:
            print_output(error("TABLE_NOT_FOUND", f"Table '{schema_name}.{table_name}' not found", fmt))
            return

        ddl = result[0]["hg_dump_script"]

        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.dump", sql=dump_sql, dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms, extra={"table": table})

        if fmt == FORMAT_JSON:
            print_output(success({"schema": schema_name, "table": table_name, "ddl": ddl}))
        else:
            print_output(ddl)
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.dump", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.dump", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@schema_cmd.command("size")
@click.argument("table")
@click.pass_context
def size_cmd(ctx: click.Context, table: str) -> None:
    """Get storage size of a table.

    TABLE should be in format 'schema_name.table_name'.

    \b
    Examples:
      hologres schema size public.my_table
      hologres schema size myschema.orders
    """
    dsn = ctx.obj.get("dsn")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Parse schema.table format
        if "." in table:
            schema_name, table_name = table.rsplit(".", 1)
        else:
            schema_name, table_name = "public", table

        # Validate identifiers to prevent SQL injection
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")

        full_table_name = f"{schema_name}.{table_name}"

        # Use psycopg.sql.Identifier for safe identifier escaping
        query = sql.SQL(
            "SELECT pg_size_pretty(pg_relation_size({})) AS size, "
            "pg_relation_size({}) AS size_bytes"
        ).format(
            sql.Identifier(schema_name, table_name),
            sql.Identifier(schema_name, table_name),
        )
        size_sql = query.as_string(conn.conn)
        result = conn.execute(size_sql)

        if not result or not result[0]:
            print_output(error("TABLE_NOT_FOUND", f"Table '{full_table_name}' not found", fmt))
            return

        size_pretty = result[0]["size"]
        size_bytes = result[0]["size_bytes"]

        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.size", sql=size_sql, dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms, extra={"table": table})

        if fmt == FORMAT_JSON:
            print_output(success({
                "schema": schema_name,
                "table": table_name,
                "size": size_pretty,
                "size_bytes": size_bytes,
            }))
        else:
            print_output(f"{full_table_name}: {size_pretty}")
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.size", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("schema.size", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
