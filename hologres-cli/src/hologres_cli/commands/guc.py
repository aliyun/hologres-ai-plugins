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
    success_rows,
)
from .schema import _validate_identifier


# Common Hologres GUC parameters: (name, default, description)
HOLOGRES_GUC_CATALOG = [
    # Auto Analyze
    ("hg_enable_start_auto_analyze_worker", "on", "开启 Auto Analyze (V1.1+)"),
    ("hg_auto_check_table_changes_interval", "10min", "表变更检查间隔"),
    ("hg_auto_check_foreign_table_changes_interval", "4h", "外部表变更检查间隔"),
    ("hg_auto_analyze_max_sample_row_count", "16777216", "Auto Analyze 最大采样行数"),
    ("hg_fixed_api_modify_max_delay_interval", "3d", "Fixed Plan 最大延迟间隔"),
    # MaxCompute foreign table
    ("hg_foreign_table_max_partition_limit", "0 (v3.0.7+)", "外部表分区数限制 (0=不限制, 范围0-1024)"),
    ("hg_experimental_query_batch_size", "8192", "MaxCompute 查询批次大小"),
    ("hg_foreign_table_split_size", "64", "外部表 split 大小"),
    ("hg_foreign_table_executor_max_dop", "Core数", "外部表查询最大并行度 (最大128)"),
    ("hg_foreign_table_executor_dml_max_dop", "32", "外部表 DML 最大并行度"),
    ("hg_enable_access_odps_orc_via_holo", "on", "通过 Holo 引擎读取 MaxCompute ORC"),
    # Query optimization
    ("optimizer_join_order", "exhaustive", "Join 顺序策略 (exhaustive/query/greedy)"),
    ("optimizer_force_multistage_agg", "off", "强制多阶段聚合"),
    ("hg_experimental_enable_result_cache", "on", "查询结果缓存"),
    # Timeout & connection
    ("statement_timeout", "8h", "活跃 Query 超时时间"),
    ("idle_in_transaction_session_timeout", "10min", "空闲事务超时时间"),
    ("idle_session_timeout", "0", "空闲连接超时 (0=不自动释放)"),
    # Data & security
    ("hg_anon_enable", "off", "数据脱敏功能"),
    ("hg_experimental_encryption_options", "off", "数据存储加密"),
    # Misc
    ("timezone", "PRC", "时区设置"),
    ("hg_experimental_enable_create_table_like_properties", "off", "CREATE TABLE LIKE 复制表属性"),
    ("hg_experimental_affect_row_multiple_times_keep_first", "off", "UPSERT 源数据重复时保留首条"),
    ("hg_experimental_affect_row_multiple_times_keep_last", "off", "UPSERT 源数据重复时保留末条"),
    ("hg_experimental_enable_read_replica", "on", "单实例多副本高可用"),
    ("hg_experimental_display_query_id", "off", "通过 NOTICE 打印 Query ID"),
    ("hg_experimental_approx_count_distinct_precision", "17", "APPROX_COUNT_DISTINCT 精度 (12-20)"),
    ("hg_experimental_functions_use_pg_implementation", "-", "时间函数使用PG实现 (支持0000-9999年)"),
]

# Flat list of parameter names for backward compatibility
HOLOGRES_GUC_PARAMS = [item[0] for item in HOLOGRES_GUC_CATALOG]


def _build_guc_catalog_text() -> str:
    """Build the formatted GUC parameter catalog."""
    categories = [
        ("Auto Analyze", [
            "hg_enable_start_auto_analyze_worker",
            "hg_auto_check_table_changes_interval",
            "hg_auto_check_foreign_table_changes_interval",
            "hg_auto_analyze_max_sample_row_count",
            "hg_fixed_api_modify_max_delay_interval",
        ]),
        ("MaxCompute Foreign Table", [
            "hg_foreign_table_max_partition_limit",
            "hg_experimental_query_batch_size",
            "hg_foreign_table_split_size",
            "hg_foreign_table_executor_max_dop",
            "hg_foreign_table_executor_dml_max_dop",
            "hg_enable_access_odps_orc_via_holo",
        ]),
        ("Query Optimization", [
            "optimizer_join_order",
            "optimizer_force_multistage_agg",
            "hg_experimental_enable_result_cache",
        ]),
        ("Timeout & Connection", [
            "statement_timeout",
            "idle_in_transaction_session_timeout",
            "idle_session_timeout",
        ]),
        ("Data & Security", [
            "hg_anon_enable",
            "hg_experimental_encryption_options",
        ]),
        ("Misc", [
            "timezone",
            "hg_experimental_enable_create_table_like_properties",
            "hg_experimental_affect_row_multiple_times_keep_first",
            "hg_experimental_affect_row_multiple_times_keep_last",
            "hg_experimental_enable_read_replica",
            "hg_experimental_display_query_id",
            "hg_experimental_approx_count_distinct_precision",
            "hg_experimental_functions_use_pg_implementation",
        ]),
    ]
    catalog_map = {item[0]: item for item in HOLOGRES_GUC_CATALOG}
    lines = []
    for cat_name, param_names in categories:
        lines.append(f"  [{cat_name}]")
        for name in param_names:
            entry = catalog_map.get(name)
            if entry:
                _, default, desc = entry
                lines.append(f"    {name}")
                lines.append(f"        default={default}  {desc}")
        lines.append("")
    return "\n".join(lines)


class GucGroup(click.Group):
    """Custom Click group that appends GUC catalog to help output."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Override to append pre-formatted GUC catalog without wrapping."""
        super().format_help(ctx, formatter)
        # Write the GUC catalog directly to the formatter buffer
        # This bypasses Click's text wrapping
        formatter.write("\nKnown Hologres GUC Parameters:\n\n")
        formatter.write(_build_guc_catalog_text())
        formatter.write("\n")


@click.group("guc", cls=GucGroup)
def guc_cmd() -> None:
    """GUC parameter management commands."""
    pass


@guc_cmd.command("list")
@click.option("--filter", "-q", default=None, help="Filter parameters by keyword")
@click.pass_context
def list_cmd(ctx: click.Context, filter: str | None) -> None:
    """List common Hologres GUC parameters with their current values.

    \b
    Examples:
      hologres guc list
      hologres guc list --filter timeout
      hologres guc list -q optimizer
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    params_to_show = HOLOGRES_GUC_PARAMS
    if filter:
        keyword = filter.lower()
        params_to_show = [p for p in params_to_show if keyword in p.lower()]

    rows = []
    try:
        for param in params_to_show:
            try:
                show_sql = psql.SQL("SHOW {}").format(psql.Identifier(param))
                result = conn.execute(show_sql.as_string(conn.conn))
                value = result[0][list(result[0].keys())[0]] if result else None
                rows.append({"param": param, "value": value})
            except Exception:
                rows.append({"param": param, "value": "(not available)"})

        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.list", dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms)

        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.list", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


@guc_cmd.command("show")
@click.argument("param_name")
@click.pass_context
def show_cmd(ctx: click.Context, param_name: str) -> None:
    """Show the current value of a GUC parameter.

    PARAM_NAME: GUC parameter name (e.g., optimizer_join_order).
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        _validate_identifier(param_name, "GUC parameter name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
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
@click.option("--scope", type=click.Choice(["database", "session"]),
              default="database", help="Scope: 'database' (persistent) or 'session' (current only)")
@click.pass_context
def set_cmd(ctx: click.Context, param_name: str, value: str, scope: str) -> None:
    """Set a GUC parameter at database or session level.

    Default scope is 'database' (persistent via ALTER DATABASE).
    Use --scope session for current session only (via SET).

    \b
    Examples:
      hologres guc set optimizer_join_order query
      hologres guc set statement_timeout '5min'
      hologres guc set hg_foreign_table_executor_max_dop 32 --scope session

    \b
    PARAM_NAME: GUC parameter name (e.g., optimizer_join_order).
    VALUE: Parameter value (e.g., 'query' or 'on').
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        _validate_identifier(param_name, "GUC parameter name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        if scope == "session":
            set_sql = psql.SQL("SET {} = {}").format(
                psql.Identifier(param_name),
                psql.Literal(value),
            )
            final_sql = set_sql.as_string(conn.conn)
            conn.execute(final_sql)

            duration_ms = (time.time() - start_time) * 1000
            log_operation("guc.set", sql=final_sql, dsn_masked=conn.masked_dsn,
                          success=True, duration_ms=duration_ms)

            if fmt == FORMAT_JSON:
                print_output(success({
                    "param": param_name,
                    "value": value,
                    "scope": "session",
                }))
            else:
                print_output(
                    f"GUC parameter '{param_name}' set to '{value}' "
                    f"at session level (current connection only)."
                )
        else:
            dbname = conn.database
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


@guc_cmd.command("reset")
@click.argument("param_name")
@click.option("--scope", type=click.Choice(["database", "session"]),
              default="database", help="Scope: 'database' (persistent) or 'session' (current only)")
@click.pass_context
def reset_cmd(ctx: click.Context, param_name: str, scope: str) -> None:
    """Reset a GUC parameter to its default value.

    Default scope is 'database' (persistent via ALTER DATABASE RESET).
    Use --scope session for current session only (via RESET).

    \b
    Examples:
      hologres guc reset statement_timeout
      hologres guc reset optimizer_join_order --scope session
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        _validate_identifier(param_name, "GUC parameter name")
    except ValueError as e:
        print_output(error("INVALID_INPUT", str(e), fmt))
        return

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        if scope == "session":
            reset_sql = psql.SQL("RESET {}").format(
                psql.Identifier(param_name),
            )
            final_sql = reset_sql.as_string(conn.conn)
            conn.execute(final_sql)

            duration_ms = (time.time() - start_time) * 1000
            log_operation("guc.reset", sql=final_sql, dsn_masked=conn.masked_dsn,
                          success=True, duration_ms=duration_ms)

            if fmt == FORMAT_JSON:
                print_output(success({
                    "param": param_name,
                    "reset": True,
                    "scope": "session",
                }))
            else:
                print_output(
                    f"GUC parameter '{param_name}' reset to default "
                    f"at session level."
                )
        else:
            dbname = conn.database
            alter_sql = psql.SQL("ALTER DATABASE {} RESET {}").format(
                psql.Identifier(dbname),
                psql.Identifier(param_name),
            )
            final_sql = alter_sql.as_string(conn.conn)
            conn.execute(final_sql)

            duration_ms = (time.time() - start_time) * 1000
            log_operation("guc.reset", sql=final_sql, dsn_masked=conn.masked_dsn,
                          success=True, duration_ms=duration_ms)

            if fmt == FORMAT_JSON:
                print_output(success({
                    "param": param_name,
                    "reset": True,
                    "scope": "database",
                    "database": dbname,
                }))
            else:
                print_output(
                    f"GUC parameter '{param_name}' reset to default "
                    f"at database level (database: {dbname}). "
                    f"Change takes effect for new sessions."
                )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("guc.reset", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
