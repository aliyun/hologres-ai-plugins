"""Dynamic Table management commands (V3.1+ new syntax).

Provides create, list, show, refresh, alter, drop, convert, ddl, lineage,
storage, and state-size subcommands for managing Hologres Dynamic Tables.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_conn(ctx: click.Context):
    """Get connection from context."""
    profile = ctx.obj.get("profile")
    return get_connection(profile=profile)


def _execute_sql(ctx: click.Context, sql: str, dry_run: bool = False) -> Optional[str]:
    """Execute SQL or print it if dry_run. Returns error string on failure, None on success."""
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if dry_run:
        print_output(success({"sql": sql, "dry_run": True}, fmt, message="SQL generated (dry-run mode)"))
        return None

    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return str(e)

    start_time = time.time()
    try:
        rows = conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt", sql=sql, dsn_masked=conn.masked_dsn, success=True, duration_ms=duration_ms)

        if rows:
            print_output(success_rows(rows, fmt))
        else:
            print_output(success({"sql": sql, "executed": True}, fmt, message="Statement executed successfully"))
        return None
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt", sql=sql, dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
        return str(e)
    finally:
        conn.close()


def _build_create_sql(
    table: str,
    query: str,
    freshness: str,
    refresh_mode: Optional[str],
    auto_refresh: Optional[bool],
    cdc_format: Optional[str],
    computing_resource: Optional[str],
    serverless_cores: Optional[int],
    logical_partition_key: Optional[str],
    partition_active_time: Optional[str],
    partition_time_format: Optional[str],
    orientation: Optional[str],
    table_group: Optional[str],
    distribution_key: Optional[str],
    clustering_key: Optional[str],
    event_time_column: Optional[str],
    bitmap_columns: Optional[str],
    dictionary_encoding_columns: Optional[str],
    ttl: Optional[int],
    storage_mode: Optional[str],
    columns: Optional[str],
    refresh_gucs: Tuple[str, ...],
) -> str:
    """Build CREATE DYNAMIC TABLE SQL statement (V3.1+ syntax)."""

    # Table name and columns
    col_clause = ""
    if columns:
        col_clause = f" ({columns})"

    # Logical partition clause
    partition_clause = ""
    if logical_partition_key:
        partition_clause = f"\nLOGICAL PARTITION BY LIST({logical_partition_key})"

    # WITH properties
    props = []
    props.append(f"freshness = '{freshness}'")

    if auto_refresh is not None:
        props.append(f"auto_refresh_enable = {'true' if auto_refresh else 'false'}")
    if refresh_mode:
        props.append(f"auto_refresh_mode = '{refresh_mode}'")
    if cdc_format:
        props.append(f"base_table_cdc_format = '{cdc_format}'")
    if partition_active_time:
        props.append(f"auto_refresh_partition_active_time = '{partition_active_time}'")
    if partition_time_format:
        props.append(f"partition_key_time_format = '{partition_time_format}'")
    if computing_resource:
        props.append(f"computing_resource = '{computing_resource}'")
    if serverless_cores is not None:
        props.append(
            f"refresh_guc_hg_experimental_serverless_computing_required_cores = '{serverless_cores}'"
        )

    # Table properties
    if orientation:
        props.append(f"orientation = '{orientation}'")
    if table_group:
        props.append(f"table_group = '{table_group}'")
    if distribution_key:
        props.append(f"distribution_key = '{distribution_key}'")
    if clustering_key:
        props.append(f"clustering_key = '{clustering_key}'")
    if event_time_column:
        props.append(f"event_time_column = '{event_time_column}'")
    if bitmap_columns:
        props.append(f"bitmap_columns = '{bitmap_columns}'")
    if dictionary_encoding_columns:
        props.append(f"dictionary_encoding_columns = '{dictionary_encoding_columns}'")
    if ttl is not None:
        props.append(f"time_to_live_in_seconds = '{ttl}'")
    if storage_mode:
        props.append(f"storage_mode = '{storage_mode}'")

    # GUC parameters
    for guc in refresh_gucs:
        if "=" in guc:
            k, v = guc.split("=", 1)
            props.append(f"refresh_guc_{k.strip()} = '{v.strip()}'")

    with_clause = ",\n  ".join(props)

    sql = (
        f"CREATE DYNAMIC TABLE {table}{col_clause}{partition_clause}\n"
        f"WITH (\n  {with_clause}\n)\n"
        f"AS\n{query.rstrip(';')}"
    )
    return sql


def _parse_table_name(table: str) -> Tuple[str, str]:
    """Parse [schema.]table into (schema, table). Default schema: public."""
    if "." in table:
        parts = table.split(".", 1)
        return parts[0], parts[1]
    return "public", table


# ---------------------------------------------------------------------------
# Command group
# ---------------------------------------------------------------------------

@click.group("dt")
@click.pass_context
def dt_cmd(ctx: click.Context) -> None:
    """Dynamic Table management (V3.1+ new syntax).

    \b
    Manage Hologres Dynamic Tables: create, list, show, refresh, alter,
    drop, convert, ddl, lineage, storage, state-size.

    \b
    Examples:
      hologres dt create --table my_dt --freshness "10 minutes" --query "SELECT ..."
      hologres dt list
      hologres dt show public.my_dt
      hologres dt ddl public.my_dt
      hologres dt lineage public.my_dt
      hologres dt storage public.my_dt
      hologres dt state-size public.my_dt
      hologres dt refresh public.my_dt
      hologres dt alter public.my_dt --freshness "30 minutes"
      hologres dt drop public.my_dt --confirm
      hologres dt convert public.my_dt
    """
    pass


# ---------------------------------------------------------------------------
# dt create
# ---------------------------------------------------------------------------

@dt_cmd.command("create")
@click.option(
    "--table", "-t", required=True,
    help="Table name in format [schema.]table_name. "
         "Example: public.my_dynamic_table")
@click.option(
    "--query", "-q", required=True,
    help="The SQL query that defines the Dynamic Table data (AS <query> clause). "
         "Example: \"SELECT col1, SUM(col2) FROM base_table GROUP BY col1\"")
@click.option(
    "--freshness", required=True,
    help="[REQUIRED] Data freshness target. The engine auto-schedules refresh. "
         "Format: '<num> {minutes|hours}'. Min: 1 minutes. "
         "Examples: '10 minutes', '1 hours', '30 minutes'")
@click.option(
    "--refresh-mode", type=click.Choice(["auto", "full", "incremental"]), default=None,
    help="Refresh mode. "
         "auto: engine picks incremental if supported, else full (default). "
         "incremental: only refresh changed data (faster). "
         "full: refresh entire dataset each time.")
@click.option(
    "--auto-refresh/--no-auto-refresh", default=None,
    help="Enable/disable automatic refresh. Default: enabled. "
         "When disabled, refresh only via manual REFRESH command.")
@click.option(
    "--cdc-format", type=click.Choice(["stream", "binlog"]), default=None,
    help="CDC format for incremental refresh. "
         "stream (default): file-level change detection, no extra storage. "
         "binlog: consume base table binlog (requires binlog enabled). "
         "Note: row-store tables only support binlog.")
@click.option(
    "--computing-resource", default=None,
    help="Computing resource for refresh. "
         "Values: 'local', 'serverless' (default), or '<warehouse_name>' (V4.0.7+).")
@click.option(
    "--serverless-cores", type=int, default=None,
    help="Serverless computing cores for refresh. "
         "Only when computing-resource=serverless. Example: 32")
@click.option(
    "--logical-partition-key", default=None,
    help="Create as logical partition table. Specify partition column. "
         "Requires --partition-active-time and --partition-time-format. "
         "Example: --logical-partition-key ds")
@click.option(
    "--partition-active-time", default=None,
    help="Active partition refresh window (logical partition only). "
         "Format: '<num> {minutes|hours|days}'. "
         "Example: '2 days' refreshes partitions from last 2 days.")
@click.option(
    "--partition-time-format", default=None,
    type=click.Choice(["YYYYMMDDHH24", "YYYY-MM-DD-HH24", "YYYY-MM-DD_HH24",
                        "YYYYMMDD", "YYYY-MM-DD", "YYYYMM", "YYYY-MM", "YYYY"]),
    help="Partition key time format. Must match your partition column format. "
         "TEXT/VARCHAR: all formats. INT: YYYYMMDDHH24/YYYYMMDD/YYYYMM/YYYY. "
         "DATE: YYYY-MM-DD only.")
@click.option(
    "--orientation", type=click.Choice(["column", "row", "row,column"]), default=None,
    help="Storage orientation. Default: column (best for analytics).")
@click.option(
    "--table-group", default=None,
    help="Table Group name. Default: database default Table Group.")
@click.option(
    "--distribution-key", default=None,
    help="Distribution key columns (comma-separated). "
         "Example: 'user_id,order_id'")
@click.option(
    "--clustering-key", default=None,
    help="Clustering key with optional sort order. "
         "Format: 'col1[:asc],col2[:asc]'. Example: 'created_at:asc'")
@click.option(
    "--event-time-column", default=None,
    help="Event time column (Segment Key). Example: 'created_at'")
@click.option(
    "--bitmap-columns", default=None,
    help="Bitmap index columns (comma-separated). Default: TEXT columns. "
         "Example: 'status,category,region'")
@click.option(
    "--dictionary-encoding-columns", default=None,
    help="Dictionary encoding columns (comma-separated). Default: TEXT columns. "
         "Example: 'country,gender'")
@click.option(
    "--ttl", type=int, default=None,
    help="Data time-to-live in seconds. Default: permanent. "
         "Example: 2592000 (30 days)")
@click.option(
    "--storage-mode", type=click.Choice(["hot", "cold"]), default=None,
    help="Storage tier. hot (default): SSD. cold: HDD/OSS (cheaper).")
@click.option(
    "--columns", default=None,
    help="Explicit column names (comma-separated). Do NOT specify data types. "
         "Example: 'col1,col2,col3'")
@click.option(
    "--refresh-guc", multiple=True,
    help="GUC params for refresh (repeatable). Format: key=value. "
         "Example: --refresh-guc timezone=GMT-8:00")
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Only generate and display the SQL without executing.")
@click.pass_context
def dt_create(ctx: click.Context, table: str, query: str, freshness: str,
              refresh_mode: Optional[str], auto_refresh: Optional[bool],
              cdc_format: Optional[str], computing_resource: Optional[str],
              serverless_cores: Optional[int], logical_partition_key: Optional[str],
              partition_active_time: Optional[str], partition_time_format: Optional[str],
              orientation: Optional[str], table_group: Optional[str],
              distribution_key: Optional[str], clustering_key: Optional[str],
              event_time_column: Optional[str], bitmap_columns: Optional[str],
              dictionary_encoding_columns: Optional[str], ttl: Optional[int],
              storage_mode: Optional[str], columns: Optional[str],
              refresh_guc: Tuple[str, ...], dry_run: bool) -> None:
    """Create a Dynamic Table using V3.1+ syntax.

    \b
    Minimal example:
      hologres dt create -t my_dt \\
        --freshness "10 minutes" \\
        -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

    \b
    Full example with partitioning:
      hologres dt create -t ads_report \\
        --freshness "5 minutes" --refresh-mode auto \\
        --logical-partition-key ds \\
        --partition-active-time "2 days" \\
        --partition-time-format YYYY-MM-DD \\
        --computing-resource serverless --serverless-cores 32 \\
        -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

    \b
    Incremental refresh example:
      hologres dt create -t tpch_q1_incr \\
        --freshness "3 minutes" --refresh-mode incremental \\
        -q "SELECT l_returnflag, l_linestatus, COUNT(*) FROM lineitem GROUP BY 1,2"
    """
    sql = _build_create_sql(
        table=table, query=query, freshness=freshness,
        refresh_mode=refresh_mode, auto_refresh=auto_refresh,
        cdc_format=cdc_format, computing_resource=computing_resource,
        serverless_cores=serverless_cores,
        logical_partition_key=logical_partition_key,
        partition_active_time=partition_active_time,
        partition_time_format=partition_time_format,
        orientation=orientation, table_group=table_group,
        distribution_key=distribution_key, clustering_key=clustering_key,
        event_time_column=event_time_column, bitmap_columns=bitmap_columns,
        dictionary_encoding_columns=dictionary_encoding_columns,
        ttl=ttl, storage_mode=storage_mode, columns=columns,
        refresh_gucs=refresh_guc,
    )
    _execute_sql(ctx, sql, dry_run=dry_run)


# ---------------------------------------------------------------------------
# dt list
# ---------------------------------------------------------------------------

DT_LIST_SQL = """\
SELECT DISTINCT
    p.dynamic_table_namespace AS schema_name,
    p.dynamic_table_name AS table_name,
    MAX(CASE WHEN p.property_key = 'auto_refresh_mode' THEN p.property_value END) AS refresh_mode,
    MAX(CASE WHEN p.property_key = 'freshness' THEN p.property_value END) AS freshness,
    MAX(CASE WHEN p.property_key = 'auto_refresh_enable' THEN p.property_value END) AS auto_refresh,
    MAX(CASE WHEN p.property_key = 'computing_resource' THEN p.property_value END) AS computing_resource
FROM hologres.hg_dynamic_table_properties p
GROUP BY p.dynamic_table_namespace, p.dynamic_table_name
ORDER BY p.dynamic_table_namespace, p.dynamic_table_name\
"""


@dt_cmd.command("list")
@click.pass_context
def dt_list(ctx: click.Context) -> None:
    """List all Dynamic Tables in the current database.

    \b
    Displays: schema, table name, refresh mode, freshness,
    auto-refresh status, and computing resource.

    \b
    Examples:
      hologres dt list
      hologres dt list -f table
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        rows = conn.execute(DT_LIST_SQL)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.list", sql=DT_LIST_SQL, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.list", sql=DT_LIST_SQL, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# dt show
# ---------------------------------------------------------------------------

DT_SHOW_SQL = """\
SELECT
    p.property_key,
    p.property_value
FROM hologres.hg_dynamic_table_properties p
WHERE p.dynamic_table_namespace = %s
  AND p.dynamic_table_name = %s
ORDER BY p.property_key\
"""


@dt_cmd.command("show")
@click.argument("table")
@click.pass_context
def dt_show(ctx: click.Context, table: str) -> None:
    """Show properties of a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name (default schema: public).

    \b
    Displays all configured properties including refresh mode, freshness,
    computing resource, table properties, and GUC settings.

    \b
    Examples:
      hologres dt show my_dynamic_table
      hologres dt show public.my_dt -f table
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    schema, tbl = _parse_table_name(table)

    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        rows = conn.execute(DT_SHOW_SQL, (schema, tbl))
        duration_ms = (time.time() - start_time) * 1000
        if not rows:
            log_operation("dt.show", dsn_masked=conn.masked_dsn, success=False,
                          error_code="NOT_FOUND", duration_ms=duration_ms)
            print_output(error("NOT_FOUND",
                               f"Dynamic Table '{table}' not found or has no properties.", fmt))
        else:
            log_operation("dt.show", dsn_masked=conn.masked_dsn, success=True,
                          row_count=len(rows), duration_ms=duration_ms)
            print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.show", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# dt refresh
# ---------------------------------------------------------------------------

@dt_cmd.command("refresh")
@click.argument("table")
@click.option(
    "--partition", default=None,
    help="Partition value to refresh. Format: \"partition_key = 'value'\". "
         "Example: --partition \"ds = '2025-04-01'\"")
@click.option(
    "--mode", type=click.Choice(["full", "incremental"]), default=None,
    help="Override refresh mode for this execution.")
@click.option(
    "--overwrite", is_flag=True, default=False,
    help="Use REFRESH OVERWRITE syntax to replace existing partition data. "
         "Typically for historical data correction with --partition.")
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Only generate and display the SQL without executing.")
@click.pass_context
def dt_refresh(ctx: click.Context, table: str, partition: Optional[str],
               mode: Optional[str], overwrite: bool, dry_run: bool) -> None:
    """Manually trigger a refresh for a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name.

    \b
    Examples:
      hologres dt refresh my_dt
      hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full
      hologres dt refresh my_dt --dry-run
    """
    if overwrite:
        sql = f"REFRESH OVERWRITE DYNAMIC TABLE {table}"
    else:
        sql = f"REFRESH DYNAMIC TABLE {table}"

    if partition:
        sql += f"\nPARTITION ({partition})"

    with_parts = []
    if mode:
        with_parts.append(f"refresh_mode = '{mode}'")
    if with_parts:
        sql += f"\nWITH (\n  {', '.join(with_parts)}\n)"

    _execute_sql(ctx, sql, dry_run=dry_run)


# ---------------------------------------------------------------------------
# dt alter
# ---------------------------------------------------------------------------

@dt_cmd.command("alter")
@click.argument("table")
@click.option("--freshness", default=None,
              help="New freshness target. Example: '30 minutes'")
@click.option("--auto-refresh/--no-auto-refresh", default=None,
              help="Enable or disable automatic refresh.")
@click.option("--refresh-mode", type=click.Choice(["auto", "full", "incremental"]), default=None,
              help="Change refresh mode.")
@click.option("--computing-resource", default=None,
              help="Change computing resource: 'local', 'serverless', or warehouse name.")
@click.option("--serverless-cores", type=int, default=None,
              help="Change serverless computing cores.")
@click.option("--partition-active-time", default=None,
              help="Change active partition time window (logical partition only). "
                   "Example: '3 days'")
@click.option("--refresh-guc", multiple=True,
              help="Set/update GUC parameters. Format: key=value (repeatable).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only generate and display the SQL without executing.")
@click.pass_context
def dt_alter(ctx: click.Context, table: str, freshness: Optional[str],
             auto_refresh: Optional[bool], refresh_mode: Optional[str],
             computing_resource: Optional[str], serverless_cores: Optional[int],
             partition_active_time: Optional[str],
             refresh_guc: Tuple[str, ...], dry_run: bool) -> None:
    """Alter properties of a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name.

    \b
    Examples:
      hologres dt alter my_dt --freshness "30 minutes"
      hologres dt alter my_dt --no-auto-refresh
      hologres dt alter my_dt --refresh-mode full --computing-resource serverless
      hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    props = []

    if freshness:
        props.append(f"freshness = '{freshness}'")
    if auto_refresh is not None:
        props.append(f"auto_refresh_enable = {'true' if auto_refresh else 'false'}")
    if refresh_mode:
        props.append(f"auto_refresh_mode = '{refresh_mode}'")
    if computing_resource:
        props.append(f"computing_resource = '{computing_resource}'")
    if serverless_cores is not None:
        props.append(
            f"refresh_guc_hg_experimental_serverless_computing_required_cores = '{serverless_cores}'"
        )
    if partition_active_time:
        props.append(f"auto_refresh_partition_active_time = '{partition_active_time}'")

    for guc in refresh_guc:
        if "=" in guc:
            k, v = guc.split("=", 1)
            props.append(f"refresh_guc_{k.strip()} = '{v.strip()}'")

    if not props:
        print_output(error("NO_CHANGES",
                           "No properties specified to alter. Use --help for options.", fmt))
        return

    joined = ",\n  ".join(props)
    sql = f"ALTER DYNAMIC TABLE {table} SET (\n  {joined}\n)"
    _execute_sql(ctx, sql, dry_run=dry_run)


# ---------------------------------------------------------------------------
# dt drop
# ---------------------------------------------------------------------------

@dt_cmd.command("drop")
@click.argument("table")
@click.option("--if-exists", is_flag=True, default=False,
              help="Add IF EXISTS clause. No error if table does not exist.")
@click.option("--confirm", is_flag=True, default=False,
              help="[REQUIRED to execute] Confirm the drop operation. "
                   "Without --confirm, only dry-run SQL is shown (safety).")
@click.pass_context
def dt_drop(ctx: click.Context, table: str, if_exists: bool, confirm: bool) -> None:
    """Drop a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name.

    \b
    SAFETY: Destructive operation. By default only shows the SQL.
    Use --confirm to actually execute the DROP.

    \b
    Examples:
      hologres dt drop my_dt              # dry-run, shows SQL
      hologres dt drop my_dt --confirm    # actually drops
      hologres dt drop my_dt --if-exists --confirm
    """
    exists_clause = " IF EXISTS" if if_exists else ""
    sql = f"DROP DYNAMIC TABLE{exists_clause} {table}"
    _execute_sql(ctx, sql, dry_run=not confirm)


# ---------------------------------------------------------------------------
# dt convert
# ---------------------------------------------------------------------------

@dt_cmd.command("convert")
@click.argument("table", required=False, default=None)
@click.option("--all", "convert_all", is_flag=True, default=False,
              help="Convert ALL V3.0 Dynamic Tables to V3.1 syntax. "
                   "WARNING: auto-refresh enabled tables start refreshing immediately. "
                   "Execute during low-traffic periods.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only generate and display the SQL without executing.")
@click.pass_context
def dt_convert(ctx: click.Context, table: Optional[str], convert_all: bool,
               dry_run: bool) -> None:
    """Convert Dynamic Table from V3.0 to V3.1 syntax.

    \b
    TABLE: Table name to convert (optional if --all is used).

    \b
    Only applies to non-partition tables. For partition tables,
    recreate manually using logical partitions.

    \b
    IMPORTANT:
      - Requires Superuser privilege.
      - After conversion, auto-refresh enabled tables start refreshing immediately.
      - Execute during low-traffic periods.
      - Recommend using serverless computing for refresh isolation.

    \b
    Examples:
      hologres dt convert my_old_dt
      hologres dt convert my_old_dt --dry-run
      hologres dt convert --all
      hologres dt convert --all --dry-run
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if convert_all:
        sql = "CALL hg_upgrade_all_normal_dynamic_tables()"
    elif table:
        sql = f"CALL hg_dynamic_table_config_upgrade('{table}')"
    else:
        print_output(error("INVALID_ARGS",
                           "Please specify a table name or use --all flag. "
                           "Example: hologres dt convert my_table", fmt))
        return

    _execute_sql(ctx, sql, dry_run=dry_run)


# ---------------------------------------------------------------------------
# dt ddl
# ---------------------------------------------------------------------------

@dt_cmd.command("ddl")
@click.argument("table")
@click.pass_context
def dt_ddl(ctx: click.Context, table: str) -> None:
    """Show DDL (CREATE statement) of a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name (default schema: public).

    \b
    Uses hg_dump_script() to retrieve the full CREATE DYNAMIC TABLE statement.

    \b
    Examples:
      hologres dt ddl my_dynamic_table
      hologres dt ddl public.my_dt -f table
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = f"SELECT hg_dump_script('{table}')"
    start_time = time.time()
    try:
        rows = conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.ddl", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        if rows and rows[0].get("hg_dump_script"):
            print_output(success({"ddl": rows[0]["hg_dump_script"]}, fmt))
        else:
            print_output(error("NOT_FOUND",
                               f"Table '{table}' not found or hg_dump_script returned empty.", fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.ddl", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# dt lineage
# ---------------------------------------------------------------------------

DT_LINEAGE_SINGLE_SQL = """\
SELECT
    d.*,
    CASE WHEN k.dynamic_table_namespace IS NOT NULL THEN
        'd'
    ELSE
        c.relkind::text
    END AS base_table_type
FROM
    hologres.hg_dynamic_table_dependencies d
    LEFT JOIN pg_namespace n ON n.nspname = d.table_namespace
    LEFT JOIN pg_class c ON c.relnamespace = n.oid
        AND c.relname = d.table_name
    LEFT JOIN (
        SELECT
            dynamic_table_namespace,
            dynamic_table_name
        FROM
            hologres.hg_dynamic_table_properties
        GROUP BY
            1,
            2) k ON k.dynamic_table_namespace = d.table_namespace
    AND k.dynamic_table_name = d.table_name
WHERE
    d.dynamic_table_namespace = %s
    AND d.dynamic_table_name = %s
    AND d.dependency <> 'internal_table'\
"""

DT_LINEAGE_ALL_SQL = """\
SELECT
    d.*,
    CASE WHEN k.dynamic_table_namespace IS NOT NULL THEN
        'd'
    ELSE
        c.relkind::text
    END AS base_table_type
FROM
    hologres.hg_dynamic_table_dependencies d
    LEFT JOIN pg_namespace n ON n.nspname = d.table_namespace
    LEFT JOIN pg_class c ON c.relnamespace = n.oid
        AND c.relname = d.table_name
    LEFT JOIN (
        SELECT
            dynamic_table_namespace,
            dynamic_table_name
        FROM
            hologres.hg_dynamic_table_properties
        GROUP BY
            1,
            2) k ON k.dynamic_table_namespace = d.table_namespace
    AND k.dynamic_table_name = d.table_name
WHERE
    d.dependency <> 'internal_table'\
"""


@dt_cmd.command("lineage")
@click.argument("table", required=False, default=None)
@click.option("--all", "show_all", is_flag=True, default=False,
              help="Show lineage for ALL Dynamic Tables in the current database.")
@click.pass_context
def dt_lineage(ctx: click.Context, table: Optional[str], show_all: bool) -> None:
    """Show dependency lineage of Dynamic Tables.

    \b
    TABLE: Table name in format [schema.]table_name (optional if --all is used).

    \b
    base_table_type mapping:
      r = ordinary table, v = view, m = materialized view,
      f = foreign table, d = Dynamic Table.

    \b
    Examples:
      hologres dt lineage public.my_dt
      hologres dt lineage my_dt -f table
      hologres dt lineage --all
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if not table and not show_all:
        print_output(error("INVALID_ARGS",
                           "Specify a table name or use --all. "
                           "Example: hologres dt lineage my_dt", fmt))
        return

    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        if show_all:
            rows = conn.execute(DT_LINEAGE_ALL_SQL)
            op_name = "dt.lineage.all"
        else:
            schema, tbl = _parse_table_name(table)
            rows = conn.execute(DT_LINEAGE_SINGLE_SQL, (schema, tbl))
            op_name = "dt.lineage"

        duration_ms = (time.time() - start_time) * 1000
        log_operation(op_name, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.lineage", dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# dt storage
# ---------------------------------------------------------------------------

@dt_cmd.command("storage")
@click.argument("table")
@click.pass_context
def dt_storage(ctx: click.Context, table: str) -> None:
    """Show storage details of a Dynamic Table.

    \b
    TABLE: Table name in format [schema.]table_name (default schema: public).

    \b
    Uses hologres.hg_relation_size() to retrieve storage size breakdown.

    \b
    Examples:
      hologres dt storage my_dynamic_table
      hologres dt storage public.my_dt -f table
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = f"SELECT * FROM hologres.hg_relation_size('{table}')"
    start_time = time.time()
    try:
        rows = conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.storage", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        if rows:
            print_output(success_rows(rows, fmt))
        else:
            print_output(error("NOT_FOUND",
                               f"No storage info found for '{table}'.", fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.storage", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# dt state-size
# ---------------------------------------------------------------------------

@dt_cmd.command("state-size")
@click.argument("table")
@click.pass_context
def dt_state_size(ctx: click.Context, table: str) -> None:
    """Show state table storage size for incremental Dynamic Tables.

    \b
    TABLE: Table name in format [schema.]table_name (default schema: public).

    \b
    Incremental-refresh Dynamic Tables store intermediate aggregation
    results in a state table. This command shows its storage size.
    Note: If refresh mode is changed to full, state is auto-cleaned.

    \b
    Examples:
      hologres dt state-size my_dynamic_table
      hologres dt state-size public.my_dt -f table
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        conn = _get_conn(ctx)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = f"SELECT pg_size_pretty(hologres.hg_dynamic_table_state_size('{table}')) AS state_size"
    start_time = time.time()
    try:
        rows = conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.state-size", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        if rows:
            print_output(success({"table": table, "state_size": rows[0]["state_size"]}, fmt))
        else:
            print_output(error("NOT_FOUND",
                               f"No state info found for '{table}'.", fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("dt.state-size", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()