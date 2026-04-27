"""Partition management commands for Hologres CLI."""

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


# Whitelist of valid partition-level properties with value constraints
PARTITION_PROPERTY_VALIDATORS = {
    "keep_alive": {"valid_values": {"TRUE", "FALSE"}, "quote": False},
    "storage_mode": {"valid_values": {"hot", "cold"}, "quote": True},
    "generate_binlog": {"valid_values": {"on", "off"}, "quote": True},
}


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


def _get_partition_columns(conn, schema_name: str, table_name: str) -> list[str]:
    """Get partition column names for a logical partition table."""
    sql = """
        SELECT property_value
        FROM hologres.hg_table_properties
        WHERE table_namespace = %s
          AND table_name = %s
          AND property_key = 'logical_partition_columns'
    """
    rows = conn.execute(sql, (schema_name, table_name))
    if not rows:
        return []
    return [col.strip() for col in rows[0]["property_value"].split(",")]


def _parse_partition_value(
    partition_value: str, partition_columns: list[str]
) -> Optional[dict[str, str]]:
    """Parse --partition value into {column: value} dict.

    Supports two formats:
    - Single column without key: "2025-04-01" → {partition_columns[0]: "2025-04-01"}
    - Key=value pairs: "yy=2025,mm=04" → {"yy": "2025", "mm": "04"}
    - Single column with key: "ds=2025-04-01" → {"ds": "2025-04-01"}

    Returns None if validation fails.
    """
    if "=" in partition_value:
        # Parse key=value pairs
        pairs = {}
        for part in partition_value.split(","):
            part = part.strip()
            if "=" not in part:
                return None
            key, val = part.split("=", 1)
            pairs[key.strip()] = val.strip()
        return pairs
    else:
        # Single value without key, must have exactly one partition column
        if len(partition_columns) != 1:
            return None
        return {partition_columns[0]: partition_value}


@partition_cmd.command("create")
@click.option("--table", "-t", required=True,
              help="Table name [schema.]table_name.")
@click.option("--partition", "partition_value", required=False,
              help="Partition value (ignored for logical partition tables).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Dry-run mode.")
@click.pass_context
def create_cmd(ctx: click.Context, table: str,
               partition_value: Optional[str], dry_run: bool) -> None:
    """Create a partition (logical partition tables only).

    NOTE: Logical partition tables create partitions automatically on INSERT.
    This command is a no-op and returns a notice.

    \b
    Examples:
      hologres partition create --table my_table
      hologres partition create -t public.logs
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    print_output(success(
        {"notice": "Logical partition tables create partitions automatically "
                   "when data is inserted. No explicit CREATE PARTITION is needed."},
        fmt,
        message="No action required"
    ))


@partition_cmd.command("drop")
@click.option("--table", "-t", required=True,
              help="Table name [schema.]table_name.")
@click.option("--partition", "partition_value", required=True,
              help="Partition value. Single column: '2025-04-01'. "
                   "Multiple columns: 'yy=2025,mm=04'.")
@click.option("--confirm", is_flag=True, default=False,
              help="[REQUIRED to execute] Confirm the drop operation. "
                   "Without --confirm, only dry-run SQL is shown (safety).")
@click.pass_context
def drop_cmd(ctx: click.Context, table: str,
             partition_value: str, confirm: bool) -> None:
    """Drop a partition from a logical partition table.

    Deletes all rows matching the partition value.
    The partition disappears automatically after data is removed.

    SAFETY: Destructive operation. By default only shows the SQL.
    Use --confirm to actually execute the DELETE.

    \b
    Examples:
      hologres partition drop --table my_table --partition "2025-04-01"
      hologres partition drop -t my_table --partition "2025-04-01" --confirm
      hologres partition drop -t public.events --partition "yy=2025,mm=04" --confirm
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

        # 3. Get partition columns
        partition_cols = _get_partition_columns(conn, schema_name, table_name)
        if not partition_cols:
            print_output(error("QUERY_ERROR",
                f"Could not determine partition columns for "
                f"'{schema_name}.{table_name}'", fmt))
            return

        # 4. Parse partition value
        parsed = _parse_partition_value(partition_value, partition_cols)
        if parsed is None:
            if len(partition_cols) > 1:
                hint = (f"Table has {len(partition_cols)} partition columns "
                        f"({', '.join(partition_cols)}). "
                        f"Use format: '{','.join(c + '=<value>' for c in partition_cols)}'")
            else:
                hint = f"Invalid partition value: '{partition_value}'"
            print_output(error("INVALID_ARGS", hint, fmt))
            return

        # Validate column names match
        parsed_keys = set(parsed.keys())
        expected_keys = set(partition_cols)
        if parsed_keys != expected_keys:
            print_output(error("INVALID_ARGS",
                f"Partition column mismatch. Expected: {', '.join(partition_cols)}. "
                f"Got: {', '.join(parsed.keys())}", fmt))
            return

        # 5. Build DELETE SQL
        where_parts = []
        params = []
        for col in partition_cols:
            where_parts.append(f"{col} = %s")
            params.append(parsed[col])

        where_clause = " AND ".join(where_parts)
        sql = f"DELETE FROM {schema_name}.{table_name} WHERE {where_clause}"

        # Build display SQL with values inlined
        display_where = " AND ".join(
            f"{col} = '{parsed[col]}'" for col in partition_cols
        )
        display_sql = f"DELETE FROM {schema_name}.{table_name} WHERE {display_where}"

        # 6. Dry-run / confirm mode
        if not confirm:
            print_output(success({"sql": display_sql, "dry_run": True}, fmt,
                                 message="SQL generated (dry-run mode)"))
            return

        # Execute
        conn.execute(sql, tuple(params))
        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.drop", sql=display_sql,
                      dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms)
        print_output(success({"sql": display_sql, "executed": True}, fmt,
                             message="Partition dropped successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.drop", dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@partition_cmd.command("list")
@click.option("--table", "-t", required=True,
              help="Table name [schema.]table_name.")
@click.pass_context
def list_cmd(ctx: click.Context, table: str) -> None:
    """List partitions of a logical partition table.

    \b
    Examples:
      hologres partition list --table my_table
      hologres partition list -t public.logs
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


def _build_partition_alter_sql(
    schema_name: str,
    table_name: str,
    partition: dict[str, str],
    set_props: dict[str, str],
) -> str:
    """Build ALTER TABLE ... PARTITION(...) SET (...) SQL."""
    full_table = f"{schema_name}.{table_name}"

    # Build PARTITION clause
    parts = ", ".join(f"{col} = '{val}'" for col, val in partition.items())
    partition_str = f"PARTITION ({parts})"

    # Build SET clause
    props_str = ",\n    ".join(f"{k} = {v}" for k, v in set_props.items())
    return f"ALTER TABLE {full_table}\n{partition_str}\nSET (\n    {props_str})"


def _parse_partition_set_props(set_props: tuple[str, ...]) -> Optional[dict[str, str]]:
    """Parse --set 'key=value' arguments into validated {property: formatted_value} dict.

    Returns None if validation fails.
    """
    result: dict[str, str] = {}
    for prop_str in set_props:
        if "=" not in prop_str:
            return None
        key, value = prop_str.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key not in PARTITION_PROPERTY_VALIDATORS:
            return None

        validator = PARTITION_PROPERTY_VALIDATORS[key]
        # Normalize value for comparison (case-insensitive)
        if value.upper() not in {v.upper() for v in validator["valid_values"]}:
            return None

        # Format value for SQL
        if validator["quote"]:
            result[key] = f"'{value}'"
        else:
            result[key] = value.upper()

    return result


@partition_cmd.command("alter")
@click.option("--table", "-t", required=True,
              help="Table name [schema.]table_name.")
@click.option("--partition", "partition_value", required=True,
              help="Partition value. Format: 'col=value' or 'col1=v1,col2=v2'.")
@click.option("--set", "set_props", required=True, multiple=True,
              help="Set partition property. Format: 'key=value'. "
                   "Valid keys: keep_alive (TRUE/FALSE), storage_mode (hot/cold), "
                   "generate_binlog (on/off). Repeatable.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing.")
@click.pass_context
def alter_cmd(ctx: click.Context, table: str,
              partition_value: str, set_props: tuple[str, ...],
              dry_run: bool) -> None:
    """Alter partition properties of a logical partition table.

    Sets partition-level properties for a single partition.

    \b
    Examples:
      hologres partition alter -t my_table --partition "ds=2025-03-16" \\
        --set "keep_alive=TRUE" --set "storage_mode=hot" --dry-run
      hologres partition alter -t public.events --partition "yy=2025,mm=04" \\
        --set "keep_alive=TRUE"
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

    # Parse and validate --set properties (can be done before DB connection)
    parsed_props = _parse_partition_set_props(set_props)
    if parsed_props is None:
        valid_keys = ", ".join(PARTITION_PROPERTY_VALIDATORS.keys())
        print_output(error("INVALID_ARGS",
            f"Invalid --set value. Valid properties: {valid_keys}. "
            "Format: 'key=value'.", fmt))
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

        # 3. Get partition columns
        partition_cols = _get_partition_columns(conn, schema_name, table_name)
        if not partition_cols:
            print_output(error("QUERY_ERROR",
                f"Could not determine partition columns for "
                f"'{schema_name}.{table_name}'", fmt))
            return

        # 4. Parse partition value
        parsed = _parse_partition_value(partition_value, partition_cols)
        if parsed is None:
            if len(partition_cols) > 1:
                hint = (f"Table has {len(partition_cols)} partition columns "
                        f"({', '.join(partition_cols)}). "
                        f"Use format: '{','.join(c + '=<value>' for c in partition_cols)}'")
            else:
                hint = f"Invalid partition value: '{partition_value}'"
            print_output(error("INVALID_ARGS", hint, fmt))
            return

        # Validate column names match
        parsed_keys = set(parsed.keys())
        expected_keys = set(partition_cols)
        if parsed_keys != expected_keys:
            print_output(error("INVALID_ARGS",
                f"Partition column mismatch. Expected: {', '.join(partition_cols)}. "
                f"Got: {', '.join(parsed.keys())}", fmt))
            return

        # 5. Build SQL
        sql = _build_partition_alter_sql(schema_name, table_name, parsed, parsed_props)

        # 6. Dry-run mode
        if dry_run:
            print_output(success({"sql": sql, "dry_run": True}, fmt,
                                 message="SQL generated (dry-run mode)"))
            return

        # Execute
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.alter", sql=sql,
                      dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Partition altered successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("partition.alter", dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
