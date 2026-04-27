"""Table management commands for Hologres CLI."""

from __future__ import annotations

import time
from typing import Optional, Tuple

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


def _build_table_create_sql(
    name: str,
    columns: str,
    primary_key: Optional[str] = None,
    orientation: Optional[str] = None,
    distribution_key: Optional[str] = None,
    clustering_key: Optional[str] = None,
    event_time_column: Optional[str] = None,
    bitmap_columns: Optional[str] = None,
    dictionary_encoding_columns: Optional[str] = None,
    ttl: Optional[int] = None,
    storage_mode: Optional[str] = None,
    table_group: Optional[str] = None,
    partition_by: Optional[str] = None,
    partition_mode: Optional[str] = None,
    binlog: Optional[str] = None,
    if_not_exists: bool = False,
    binlog_ttl: Optional[int] = None,
    partition_expiration_time: Optional[str] = None,
    partition_keep_hot_window: Optional[str] = None,
    partition_require_filter: Optional[str] = None,
    partition_generate_binlog_window: Optional[str] = None,
) -> str:
    """Build CREATE TABLE SQL.

    For logical partition tables (partition_mode='logical'), uses WITH(...) syntax.
    For regular/physical partition tables, uses CALL set_table_property (compatible syntax).
    """

    # Parse schema.table
    if "." in name:
        schema_name, table_name = name.rsplit(".", 1)
    else:
        schema_name, table_name = "public", name

    full_name = f"{schema_name}.{table_name}"
    exists_clause = " IF NOT EXISTS" if if_not_exists else ""

    col_defs = columns.strip()

    # Primary key constraint
    pk_clause = ""
    if primary_key:
        pk_clause = f",\n    PRIMARY KEY ({primary_key})"

    is_logical = partition_by and partition_mode == "logical"

    if is_logical:
        return _build_logical_partition_sql(
            full_name=full_name, exists_clause=exists_clause,
            col_defs=col_defs, pk_clause=pk_clause,
            partition_by=partition_by, orientation=orientation,
            distribution_key=distribution_key, clustering_key=clustering_key,
            event_time_column=event_time_column, bitmap_columns=bitmap_columns,
            dictionary_encoding_columns=dictionary_encoding_columns,
            ttl=ttl, storage_mode=storage_mode, table_group=table_group,
            binlog=binlog, binlog_ttl=binlog_ttl,
            partition_expiration_time=partition_expiration_time,
            partition_keep_hot_window=partition_keep_hot_window,
            partition_require_filter=partition_require_filter,
            partition_generate_binlog_window=partition_generate_binlog_window,
        )

    # --- Regular / physical partition table: CALL set_table_property syntax ---
    partition_clause = ""
    if partition_by:
        partition_clause = f"\nPARTITION BY LIST ({partition_by})"

    lines = ["BEGIN;"]
    lines.append("")
    lines.append(
        f"CREATE TABLE{exists_clause} {full_name} (\n"
        f"    {col_defs}{pk_clause}\n"
        f"){partition_clause};"
    )

    # CALL set_table_property statements
    props: list[tuple[str, str]] = []
    if orientation:
        props.append(("orientation", orientation))
    if distribution_key:
        props.append(("distribution_key", distribution_key))
    if clustering_key:
        props.append(("clustering_key", clustering_key))
    if event_time_column:
        props.append(("event_time_column", event_time_column))
    if bitmap_columns:
        props.append(("bitmap_columns", bitmap_columns))
    if dictionary_encoding_columns:
        props.append(("dictionary_encoding_columns", dictionary_encoding_columns))
    if ttl is not None:
        props.append(("time_to_live_in_seconds", str(ttl)))
    if storage_mode:
        props.append(("storage_mode", storage_mode))
    if table_group:
        props.append(("table_group", table_group))
    if binlog and binlog != "none":
        props.append(("binlog.level", binlog))
    if binlog_ttl is not None:
        props.append(("binlog.ttl", str(binlog_ttl)))

    if props:
        lines.append("")
    for key, value in props:
        lines.append(
            f"CALL set_table_property('{full_name}', '{key}', '{value}');"
        )

    lines.append("")
    lines.append("COMMIT;")

    return "\n".join(lines)


def _build_logical_partition_sql(
    full_name: str,
    exists_clause: str,
    col_defs: str,
    pk_clause: str,
    partition_by: str,
    orientation: Optional[str] = None,
    distribution_key: Optional[str] = None,
    clustering_key: Optional[str] = None,
    event_time_column: Optional[str] = None,
    bitmap_columns: Optional[str] = None,
    dictionary_encoding_columns: Optional[str] = None,
    ttl: Optional[int] = None,
    storage_mode: Optional[str] = None,
    table_group: Optional[str] = None,
    binlog: Optional[str] = None,
    binlog_ttl: Optional[int] = None,
    partition_expiration_time: Optional[str] = None,
    partition_keep_hot_window: Optional[str] = None,
    partition_require_filter: Optional[str] = None,
    partition_generate_binlog_window: Optional[str] = None,
) -> str:
    """Build CREATE TABLE SQL for logical partition tables using WITH(...) syntax."""

    partition_clause = f"\nLOGICAL PARTITION BY LIST ({partition_by})"

    # Collect WITH properties (use underscore naming for WITH syntax)
    with_props: list[str] = []
    if orientation:
        with_props.append(f"orientation = '{orientation}'")
    if distribution_key:
        with_props.append(f"distribution_key = '{distribution_key}'")
    if clustering_key:
        with_props.append(f"clustering_key = '{clustering_key}'")
    if event_time_column:
        with_props.append(f"event_time_column = '{event_time_column}'")
    if bitmap_columns:
        with_props.append(f"bitmap_columns = '{bitmap_columns}'")
    if dictionary_encoding_columns:
        with_props.append(f"dictionary_encoding_columns = '{dictionary_encoding_columns}'")
    if ttl is not None:
        with_props.append(f"time_to_live_in_seconds = '{ttl}'")
    if storage_mode:
        with_props.append(f"storage_mode = '{storage_mode}'")
    if table_group:
        with_props.append(f"table_group = '{table_group}'")
    if binlog and binlog != "none":
        with_props.append(f"binlog_level = '{binlog}'")
    if binlog_ttl is not None:
        with_props.append(f"binlog_ttl = '{binlog_ttl}'")
    # Logical partition specific properties
    if partition_expiration_time:
        with_props.append(f"partition_expiration_time = '{partition_expiration_time}'")
    if partition_keep_hot_window:
        with_props.append(f"partition_keep_hot_window = '{partition_keep_hot_window}'")
    if partition_require_filter is not None:
        with_props.append(f"partition_require_filter = {partition_require_filter.upper()}")
    if partition_generate_binlog_window:
        with_props.append(f"partition_generate_binlog_window = '{partition_generate_binlog_window}'")

    with_clause = ""
    if with_props:
        formatted = ",\n    ".join(with_props)
        with_clause = f"\nWITH (\n    {formatted}\n)"

    return (
        f"CREATE TABLE{exists_clause} {full_name} (\n"
        f"    {col_defs}{pk_clause}\n"
        f"){partition_clause}{with_clause};"
    )


@click.group("table")
def table_cmd() -> None:
    """Table management commands."""
    pass


@table_cmd.command("create")
@click.option("--name", "-n", required=True,
              help="Table name [schema.]table_name (required)")
@click.option("--columns", "-c", required=True,
              help='Column definitions. Example: "col1 INT, col2 TEXT NOT NULL"')
@click.option("--primary-key", default=None,
              help="Primary key columns (comma-separated). Example: 'id' or 'id,ds'")
@click.option("--orientation", type=click.Choice(["column", "row", "row,column"]),
              default=None, help="Storage orientation (default: column)")
@click.option("--distribution-key", default=None,
              help="Distribution key columns (comma-separated)")
@click.option("--clustering-key", default=None,
              help="Clustering key with sort order. Example: 'created_at:asc'")
@click.option("--event-time-column", default=None,
              help="Event time column (Segment Key)")
@click.option("--bitmap-columns", default=None,
              help="Bitmap index columns (comma-separated)")
@click.option("--dictionary-encoding-columns", default=None,
              help="Dictionary encoding columns (comma-separated)")
@click.option("--ttl", type=int, default=None,
              help="Data TTL in seconds. Example: 2592000 (30 days)")
@click.option("--storage-mode", type=click.Choice(["hot", "cold"]),
              default=None, help="Storage tier: hot (SSD) / cold (HDD/OSS)")
@click.option("--table-group", default=None, help="Table Group name")
@click.option("--partition-by", default=None,
              help="Enable LIST partition on this column(s). "
                   "Example: 'ds' or 'yy, mm' (logical partition supports up to 2 columns)")
@click.option("--partition-mode", type=click.Choice(["physical", "logical"]),
              default=None, help="Partition mode: physical (default) / logical (V3.1+)")
@click.option("--binlog", type=click.Choice(["none", "replica"]),
              default=None, help="Binlog level: none / replica")
@click.option("--binlog-ttl", type=int, default=None,
              help="Binlog TTL in seconds (default: 2592000 = 30 days)")
@click.option("--partition-expiration-time", default=None,
              help="Partition expiration time (logical partition only). "
                   "Example: '30 day', '12 month'")
@click.option("--partition-keep-hot-window", default=None,
              help="Partition hot storage window (logical partition only). "
                   "Example: '15 day', '6 month'")
@click.option("--partition-require-filter", type=click.Choice(["true", "false"]),
              default=None,
              help="Require partition filter in queries (logical partition only)")
@click.option("--partition-generate-binlog-window", default=None,
              help="Binlog generation window for partitions (logical partition only). "
                   "Example: '3 day'")
@click.option("--if-not-exists", is_flag=True, default=False,
              help="Add IF NOT EXISTS clause")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing")
@click.pass_context
def create_cmd(ctx: click.Context, name: str, columns: str,
               primary_key: Optional[str], orientation: Optional[str],
               distribution_key: Optional[str], clustering_key: Optional[str],
               event_time_column: Optional[str], bitmap_columns: Optional[str],
               dictionary_encoding_columns: Optional[str], ttl: Optional[int],
               storage_mode: Optional[str], table_group: Optional[str],
               partition_by: Optional[str], partition_mode: Optional[str],
               binlog: Optional[str], binlog_ttl: Optional[int],
               partition_expiration_time: Optional[str],
               partition_keep_hot_window: Optional[str],
               partition_require_filter: Optional[str],
               partition_generate_binlog_window: Optional[str],
               if_not_exists: bool, dry_run: bool) -> None:
    """Create a new table.

    \b
    Examples:
      # Regular table
      hologres table create --name public.orders \\
        --columns "order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2)" \\
        --primary-key order_id --orientation column \\
        --distribution-key order_id --dry-run

    \b
      # Physical partition table
      hologres table create -n public.events \\
        -c "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload JSONB" \\
        --primary-key "event_id,ds" --partition-by ds \\
        --orientation column --dry-run

    \b
      # Logical partition table (V3.1+)
      hologres table create -n public.logs \\
        -c "a TEXT, b INT, ds DATE NOT NULL" \\
        --primary-key "b,ds" --partition-by ds \\
        --partition-mode logical --orientation column \\
        --distribution-key b \\
        --partition-expiration-time "30 day" \\
        --partition-require-filter true --dry-run
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    # Validate table name
    if "." in name:
        schema_name, table_name = name.rsplit(".", 1)
    else:
        schema_name, table_name = "public", name

    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "table name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    # Validate logical-partition-only options
    logical_only_opts = {
        "partition_expiration_time": partition_expiration_time,
        "partition_keep_hot_window": partition_keep_hot_window,
        "partition_require_filter": partition_require_filter,
        "partition_generate_binlog_window": partition_generate_binlog_window,
    }
    if partition_mode != "logical":
        used = [k for k, v in logical_only_opts.items() if v is not None]
        if used:
            opt_names = ", ".join(f"--{k.replace('_', '-')}" for k in used)
            print_output(error("INVALID_ARGS",
                f"{opt_names} can only be used with --partition-mode logical",
                fmt))
            return

    # Build SQL
    sql = _build_table_create_sql(
        name=name, columns=columns, primary_key=primary_key,
        orientation=orientation, distribution_key=distribution_key,
        clustering_key=clustering_key, event_time_column=event_time_column,
        bitmap_columns=bitmap_columns,
        dictionary_encoding_columns=dictionary_encoding_columns,
        ttl=ttl, storage_mode=storage_mode, table_group=table_group,
        partition_by=partition_by, partition_mode=partition_mode,
        binlog=binlog, if_not_exists=if_not_exists,
        binlog_ttl=binlog_ttl,
        partition_expiration_time=partition_expiration_time,
        partition_keep_hot_window=partition_keep_hot_window,
        partition_require_filter=partition_require_filter,
        partition_generate_binlog_window=partition_generate_binlog_window,
    )

    # Dry-run mode
    if dry_run:
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
        log_operation("table.create", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Table created successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.create", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


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


def _build_table_alter_sql(
    schema_name: str,
    table_name: str,
    add_columns: Tuple[str, ...] = (),
    rename_column: Optional[str] = None,
    ttl: Optional[int] = None,
    dictionary_encoding_columns: Optional[str] = None,
    bitmap_columns: Optional[str] = None,
    owner: Optional[str] = None,
    rename: Optional[str] = None,
    partition_expiration_time: Optional[str] = None,
    partition_keep_hot_window: Optional[str] = None,
    partition_require_filter: Optional[str] = None,
    binlog: Optional[str] = None,
    binlog_ttl: Optional[int] = None,
    partition_generate_binlog_window: Optional[str] = None,
) -> str:
    """Build ALTER TABLE SQL wrapped in a transaction.

    Returns a single SQL string. Multiple statements are wrapped in BEGIN/COMMIT.
    Logical partition table properties use ALTER TABLE ... SET (...) syntax.
    """
    full_table = f"{schema_name}.{table_name}"
    statements: list[str] = []

    # 1. ADD COLUMN
    if add_columns:
        add_parts = [f"ADD COLUMN {col}" for col in add_columns]
        statements.append(
            f"ALTER TABLE IF EXISTS {full_table} {', '.join(add_parts)}"
        )

    # 2. RENAME COLUMN
    if rename_column:
        old_name, new_name = rename_column.split(":", 1)
        statements.append(
            f"ALTER TABLE IF EXISTS {full_table} RENAME COLUMN {old_name.strip()} TO {new_name.strip()}"
        )

    # 3. TTL
    if ttl is not None:
        statements.append(
            f"CALL set_table_property('{full_table}', 'time_to_live_in_seconds', '{ttl}')"
        )

    # 4. dictionary_encoding_columns
    if dictionary_encoding_columns is not None:
        statements.append(
            f"CALL SET_TABLE_PROPERTY('{full_table}', 'dictionary_encoding_columns', '{dictionary_encoding_columns}')"
        )

    # 5. bitmap_columns
    if bitmap_columns is not None:
        statements.append(
            f"CALL SET_TABLE_PROPERTY('{full_table}', 'bitmap_columns', '{bitmap_columns}')"
        )

    # 6. OWNER TO
    if owner:
        statements.append(
            f"ALTER TABLE IF EXISTS {full_table} OWNER TO {owner}"
        )

    # 7. RENAME TO (last, because table name changes)
    if rename:
        statements.append(
            f"ALTER TABLE IF EXISTS {full_table} RENAME TO {rename}"
        )

    # 8. Logical partition table properties: ALTER TABLE ... SET (...)
    set_props: dict[str, str] = {}
    if partition_expiration_time:
        set_props["partition_expiration_time"] = f"'{partition_expiration_time}'"
    if partition_keep_hot_window:
        set_props["partition_keep_hot_window"] = f"'{partition_keep_hot_window}'"
    if partition_require_filter is not None:
        set_props["partition_require_filter"] = partition_require_filter.upper()
    if binlog:
        set_props["binlog_level"] = f"'{binlog}'"
    if binlog_ttl is not None:
        set_props["binlog_ttl"] = str(binlog_ttl)
    if partition_generate_binlog_window:
        set_props["partition_generate_binlog_window"] = f"'{partition_generate_binlog_window}'"

    if set_props:
        props_str = ",\n    ".join(f"{k} = {v}" for k, v in set_props.items())
        statements.append(f"ALTER TABLE {full_table} SET (\n    {props_str})")

    if not statements:
        return ""

    if len(statements) == 1:
        return statements[0]

    # Multiple statements: wrap in BEGIN/COMMIT transaction
    lines = ["BEGIN;", ""]
    for stmt in statements:
        lines.append(stmt + ";")
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines)


@table_cmd.command("alter")
@click.argument("table")
@click.option("--add-column", multiple=True,
              help='Add a column. Format: "name TYPE [constraints]". Repeatable.')
@click.option("--rename-column", default=None,
              help='Rename a column. Format: "old_name:new_name".')
@click.option("--ttl", type=int, default=None,
              help="Set data TTL in seconds.")
@click.option("--dictionary-encoding-columns", default=None,
              help='Set dictionary encoding columns. Format: "col1:on,col2:off,col3:auto".')
@click.option("--bitmap-columns", default=None,
              help='Set bitmap index columns. Format: "col1:on,col2:off".')
@click.option("--owner", default=None,
              help="Change table owner.")
@click.option("--rename", default=None,
              help="Rename the table to a new name.")
@click.option("--partition-expiration-time", default=None,
              help="Partition expiration time (logical partition table). "
                   "Example: '30 day', '12 month'")
@click.option("--partition-keep-hot-window", default=None,
              help="Partition hot storage window (logical partition table). "
                   "Example: '15 day', '6 month'")
@click.option("--partition-require-filter", type=click.Choice(["true", "false"]),
              default=None,
              help="Require partition filter in queries (logical partition table).")
@click.option("--binlog", default=None, type=click.Choice(["none", "replica"]),
              help="Binlog level: none or replica (logical partition table).")
@click.option("--binlog-ttl", type=int, default=None,
              help="Binlog TTL in seconds (logical partition table).")
@click.option("--partition-generate-binlog-window", default=None,
              help="Binlog generation window for partitions (logical partition table). "
                   "Example: '3 day'")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing.")
@click.pass_context
def alter_cmd(ctx: click.Context, table: str, add_column: Tuple[str, ...],
              rename_column: Optional[str], ttl: Optional[int],
              dictionary_encoding_columns: Optional[str],
              bitmap_columns: Optional[str],
              owner: Optional[str], rename: Optional[str],
              partition_expiration_time: Optional[str],
              partition_keep_hot_window: Optional[str],
              partition_require_filter: Optional[str],
              binlog: Optional[str],
              binlog_ttl: Optional[int],
              partition_generate_binlog_window: Optional[str],
              dry_run: bool) -> None:
    """Alter table properties.

    \b
    TABLE: Table name in format [schema.]table_name.

    \b
    Examples:
      hologres table alter my_table --add-column "age INT"
      hologres table alter my_table --ttl 3600
      hologres table alter my_table --rename-column "old_col:new_col"
      hologres table alter my_table --rename new_name --dry-run
      hologres table alter my_table --owner new_user
      hologres table alter my_table --bitmap-columns "a:on,b:off"
      hologres table alter my_table --dictionary-encoding-columns "a:on,b:auto"
      hologres table alter my_table --partition-expiration-time "60 day"
      hologres table alter my_table --partition-require-filter true --dry-run
      hologres table alter my_table --binlog replica --binlog-ttl 86400
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

    # Validate --rename-column format
    if rename_column is not None and ":" not in rename_column:
        print_output(error("INVALID_ARGS",
                           'Invalid --rename-column format. Expected "old_name:new_name".', fmt))
        return

    # Validate rename-column identifiers
    if rename_column is not None:
        old_col, new_col = rename_column.split(":", 1)
        try:
            _validate_identifier(old_col.strip(), "old column name")
            _validate_identifier(new_col.strip(), "new column name")
        except ValueError as e:
            print_output(error("INVALID_INPUT", str(e), fmt))
            return

    # Validate --rename identifier
    if rename is not None:
        try:
            _validate_identifier(rename, "new table name")
        except ValueError as e:
            print_output(error("INVALID_INPUT", str(e), fmt))
            return

    # Validate --owner identifier
    if owner is not None:
        try:
            _validate_identifier(owner, "owner name")
        except ValueError as e:
            print_output(error("INVALID_INPUT", str(e), fmt))
            return

    # Build SQL
    sql = _build_table_alter_sql(
        schema_name=schema_name,
        table_name=table_name,
        add_columns=add_column,
        rename_column=rename_column,
        ttl=ttl,
        dictionary_encoding_columns=dictionary_encoding_columns,
        bitmap_columns=bitmap_columns,
        owner=owner,
        rename=rename,
        partition_expiration_time=partition_expiration_time,
        partition_keep_hot_window=partition_keep_hot_window,
        partition_require_filter=partition_require_filter,
        binlog=binlog,
        binlog_ttl=binlog_ttl,
        partition_generate_binlog_window=partition_generate_binlog_window,
    )

    if not sql:
        print_output(error("NO_CHANGES",
                           "No properties specified to alter. Use --help for options.", fmt))
        return

    # Dry-run mode
    if dry_run:
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
        log_operation("table.alter", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Table altered successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("table.alter", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
