"""Data import/export commands for Hologres CLI."""

from __future__ import annotations

import re
import time
from pathlib import Path
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
)

# Validate schema/table names to allow only alphanumeric, underscore, and hyphen
SAFE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')


def _validate_identifier(name: str, label: str = "identifier") -> None:
    """Validate that a database identifier is safe (prevents SQL injection)."""
    if not SAFE_NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label} '{name}': only letters, digits, underscores, and hyphens allowed"
        )


def _copy_options(delimiter: str) -> str:
    """Build COPY statement options string."""
    options = "FORMAT csv, HEADER true"
    if delimiter != ",":
        options += f", DELIMITER '{delimiter}'"
    return options


@click.group("data")
def data_cmd() -> None:
    """Data import/export commands using COPY protocol."""
    pass


@data_cmd.command("export")
@click.argument("table", required=False)
@click.option("--file", "-f", "file_path", required=True, help="Output file path")
@click.option("--query", "-q", "query", default=None, help="Custom SELECT query")
@click.option("--delimiter", "-d", default=",", help="Field delimiter")
@click.pass_context
def export_cmd(ctx: click.Context, table: Optional[str], file_path: str,
               query: Optional[str], delimiter: str) -> None:
    """Export data to CSV file."""
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if not table and not query:
        print_output(error("INVALID_ARGS", "Either TABLE or --query must be provided", fmt))
        return

    start_time = time.time()
    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        if query:
            # Custom query - user is responsible for SQL safety
            source = f"({query})"
            copy_sql = f"COPY {source} TO STDOUT WITH ({_copy_options(delimiter)})"
        else:
            # Table export - use safe identifier escaping
            if "." in table:
                schema_name, table_name = table.rsplit(".", 1)
            else:
                schema_name, table_name = "public", table
            _validate_identifier(schema_name, "schema name")
            _validate_identifier(table_name, "table name")

            query_obj = sql.SQL("SELECT * FROM {}").format(
                sql.Identifier(schema_name, table_name)
            )
            source = f"({query_obj.as_string(conn.conn)})"
            copy_sql = f"COPY {source} TO STDOUT WITH ({_copy_options(delimiter)})"

        output_path = Path(file_path)
        row_count = 0
        with conn.cursor() as cur:
            with open(output_path, "wb") as f:
                with cur.copy(copy_sql) as copy:
                    for data in copy:
                        f.write(data)
                        if isinstance(data, bytes):
                            row_count += data.count(b"\n")

        if row_count > 0:
            row_count -= 1  # subtract header

        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.export", sql=copy_sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=row_count, duration_ms=duration_ms)
        print_output(success({"source": query or table, "file": str(output_path),
                              "rows": row_count, "duration_ms": round(duration_ms, 2)}, fmt))
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.export", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.export", dsn_masked=conn.masked_dsn, success=False,
                      error_code="EXPORT_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(error("EXPORT_ERROR", str(e), fmt))
    finally:
        conn.close()


@data_cmd.command("import")
@click.argument("table")
@click.option("--file", "-f", "file_path", required=True, help="Input CSV file")
@click.option("--delimiter", "-d", default=",", help="Field delimiter")
@click.option("--truncate", is_flag=True, help="Truncate table before import")
@click.pass_context
def import_cmd(ctx: click.Context, table: str, file_path: str, delimiter: str,
               truncate: bool) -> None:
    """Import data from CSV file."""
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    input_path = Path(file_path)

    # Read CSV header to determine which columns to import
    try:
        with open(input_path, "rb") as f:
            header_line = f.readline().decode().strip()
    except FileNotFoundError:
        print_output(error("FILE_NOT_FOUND", f"File not found: {file_path}", fmt))
        return

    columns = [col.strip() for col in header_line.split(delimiter)]

    start_time = time.time()
    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        if truncate:
            if "." in table:
                schema_name, table_name = table.rsplit(".", 1)
            else:
                schema_name, table_name = "public", table
            _validate_identifier(schema_name, "schema name")
            _validate_identifier(table_name, "table name")

            truncate_query = sql.SQL("TRUNCATE TABLE {}").format(
                sql.Identifier(schema_name, table_name)
            )
            with conn.cursor() as cur:
                cur.execute(truncate_query.as_string(conn.conn))

        # Build safe COPY statement
        if "." in table:
            schema_name, table_name = table.rsplit(".", 1)
        else:
            schema_name, table_name = "public", table
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")

        columns_list = sql.SQL(", ").join(sql.Identifier(col) for col in columns)
        copy_query = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
            sql.Identifier(schema_name, table_name),
            columns_list,
        )
        copy_sql = copy_query.as_string(conn.conn)

        row_count = 0
        with conn.cursor() as cur:
            with open(input_path, "rb") as f:
                with cur.copy(copy_sql) as copy:
                    while data := f.read(65536):
                        copy.write(data)
                        row_count += data.count(b"\n")

        if row_count > 0:
            row_count -= 1  # subtract header

        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.import", sql=copy_sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=row_count, duration_ms=duration_ms)
        print_output(success({"table": table, "file": str(input_path),
                              "rows": row_count, "duration_ms": round(duration_ms, 2)}, fmt))
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.import", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.import", dsn_masked=conn.masked_dsn, success=False,
                      error_code="IMPORT_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(error("IMPORT_ERROR", str(e), fmt))
    finally:
        conn.close()


@data_cmd.command("count")
@click.argument("table")
@click.option("--where", "-w", "where_clause", default=None, help="WHERE filter")
@click.pass_context
def count_cmd(ctx: click.Context, table: str, where_clause: Optional[str]) -> None:
    """Count rows in a table."""
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Parse and validate table name
        if "." in table:
            schema_name, table_name = table.rsplit(".", 1)
        else:
            schema_name, table_name = "public", table
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")

        # Build safe count query
        query_obj = sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
            sql.Identifier(schema_name, table_name)
        )
        count_sql = query_obj.as_string(conn.conn)
        if where_clause:
            count_sql += f" WHERE {where_clause}"
        rows = conn.execute(count_sql)
        count = rows[0]["count"] if rows else 0
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.count", sql=count_sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=1, duration_ms=duration_ms)
        print_output(success({"table": table, "count": count, "duration_ms": round(duration_ms, 2)}, fmt))
    except ValueError as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.count", dsn_masked=conn.masked_dsn, success=False,
                      error_code="INVALID_INPUT", error_message=str(e), duration_ms=duration_ms)
        print_output(error("INVALID_INPUT", str(e), fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("data.count", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
