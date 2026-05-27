"""Foreign table management commands for Hologres CLI.

Hologres supports CREATE/ALTER/DROP FOREIGN TABLE and IMPORT FOREIGN SCHEMA
against MaxCompute (odps_server) and DLF Paimon (paimon_server) sources.

Reference:
- CREATE FOREIGN TABLE  ... SERVER odps_server OPTIONS (project_name, table_name)
- ALTER FOREIGN TABLE   ... RENAME TO / ADD COLUMN / DROP COLUMN
- DROP FOREIGN TABLE    ... [IF EXISTS] [CASCADE | RESTRICT]
- IMPORT FOREIGN SCHEMA ... [LIMIT TO | EXCEPT] FROM SERVER ... INTO ...
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import click

from ..connection import DSNError, get_connection
from ..errors import ErrorCode
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

DEFAULT_SERVER = "odps_server"
VALID_IF_TABLE_EXIST = ("error", "ignore", "update")
VALID_IF_UNSUPPORTED_TYPE = ("error", "skip")


def _split_schema_qualified(name: str, default_schema: str = "public") -> tuple[str, str]:
    """Parse 'schema.name' into (schema, name); falls back to (default_schema, name)."""
    if "." in name:
        schema, ident = name.rsplit(".", 1)
    else:
        schema, ident = default_schema, name
    return schema, ident


def _quote_sql_string(value: str) -> str:
    """Escape a string for inclusion as a single-quoted SQL literal."""
    return value.replace("'", "''")


def _build_foreign_create_sql(
    schema_name: str,
    table_name: str,
    columns: str,
    server: str,
    project_name: str,
    odps_schema: Optional[str],
    odps_table_name: Optional[str],
    if_not_exists: bool = False,
    extra_options: Optional[dict[str, str]] = None,
) -> str:
    """Build CREATE FOREIGN TABLE SQL.

    If ``odps_schema`` is provided, ``project_name`` is rewritten to
    ``project#schema`` form to match MaxCompute three-layer model usage.
    """
    full_name = f"{schema_name}.{table_name}"
    exists_clause = " IF NOT EXISTS" if if_not_exists else ""

    effective_project = project_name
    if odps_schema:
        effective_project = f"{project_name}#{odps_schema}"

    effective_table = odps_table_name or table_name

    options: list[tuple[str, str]] = [
        ("project_name", effective_project),
        ("table_name", effective_table),
    ]
    if extra_options:
        for key, value in extra_options.items():
            options.append((key, value))

    options_str = ", ".join(
        f"{key} '{_quote_sql_string(value)}'" for key, value in options
    )

    return (
        f"CREATE FOREIGN TABLE{exists_clause} {full_name} (\n"
        f"    {columns.strip()}\n"
        f")\n"
        f"SERVER {server}\n"
        f"OPTIONS ({options_str});"
    )


def _build_foreign_alter_sql(
    schema_name: str,
    table_name: str,
    add_columns: Tuple[str, ...] = (),
    drop_columns: Tuple[str, ...] = (),
    rename: Optional[str] = None,
    if_exists: bool = True,
) -> str:
    """Build ALTER FOREIGN TABLE SQL.

    Multiple add/drop column statements are wrapped in BEGIN/COMMIT to keep
    the operation atomic; the optional RENAME runs last because it changes
    the qualified name we are referencing.
    """
    full_name = f"{schema_name}.{table_name}"
    exists_clause = " IF EXISTS" if if_exists else ""
    statements: list[str] = []

    if add_columns:
        add_parts = [f"ADD COLUMN {col.strip()}" for col in add_columns if col.strip()]
        if add_parts:
            statements.append(
                f"ALTER FOREIGN TABLE{exists_clause} {full_name} {', '.join(add_parts)}"
            )

    if drop_columns:
        drop_parts = [f"DROP COLUMN {col.strip()}" for col in drop_columns if col.strip()]
        if drop_parts:
            statements.append(
                f"ALTER FOREIGN TABLE{exists_clause} {full_name} {', '.join(drop_parts)}"
            )

    if rename:
        statements.append(
            f"ALTER FOREIGN TABLE{exists_clause} {full_name} RENAME TO {rename}"
        )

    if not statements:
        return ""
    if len(statements) == 1:
        return statements[0] + ";"

    lines = ["BEGIN;", ""]
    for stmt in statements:
        lines.append(stmt + ";")
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines)


def _build_import_foreign_schema_sql(
    remote_schema: str,
    odps_schema: Optional[str],
    server: str,
    into_schema: str,
    limit_to: Tuple[str, ...] = (),
    exclude: Tuple[str, ...] = (),
    if_table_exist: Optional[str] = None,
    if_unsupported_type: Optional[str] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """Build IMPORT FOREIGN SCHEMA SQL."""
    effective_remote = remote_schema
    if odps_schema:
        effective_remote = f"{remote_schema}#{odps_schema}"

    # remote_schema must be quoted as an SQL identifier when it contains '#'.
    remote_clause = f'"{effective_remote}"' if "#" in effective_remote else effective_remote

    parts: list[str] = [f"IMPORT FOREIGN SCHEMA {remote_clause}"]

    if limit_to and exclude:
        # Caller validates this; we keep both clauses out of the generated SQL.
        raise ValueError("--limit-to and --except are mutually exclusive")

    if limit_to:
        cols = ", ".join(t.strip() for t in limit_to if t.strip())
        parts.append(f"    LIMIT TO ({cols})")
    elif exclude:
        cols = ", ".join(t.strip() for t in exclude if t.strip())
        parts.append(f"    EXCEPT ({cols})")

    parts.append(f"    FROM SERVER {server}")
    parts.append(f"    INTO {into_schema}")

    options: list[tuple[str, str]] = []
    if if_table_exist:
        options.append(("if_table_exist", if_table_exist))
    if if_unsupported_type:
        options.append(("if_unsupported_type", if_unsupported_type))
    if prefix is not None:
        options.append(("prefix", prefix))
    if suffix is not None:
        options.append(("suffix", suffix))

    if options:
        opts_str = ", ".join(
            f"{key} '{_quote_sql_string(value)}'" for key, value in options
        )
        parts.append(f"    OPTIONS ({opts_str})")

    return "\n".join(parts) + ";"


@click.group("foreign")
def foreign_cmd() -> None:
    """Foreign table management commands (MaxCompute / DLF)."""
    pass


# ---------------------------------------------------------------------------
# foreign list
# ---------------------------------------------------------------------------
@foreign_cmd.command("list")
@click.option("--schema", "-s", "schema_name", default=None,
              help="Filter by Hologres schema name.")
@click.option("--server", default=None,
              help="Filter by foreign server name (e.g. odps_server, paimon_server).")
@click.pass_context
def list_cmd(ctx: click.Context, schema_name: Optional[str],
             server: Optional[str]) -> None:
    """List foreign tables.

    \b
    Examples:
      hologres foreign list
      hologres foreign list --schema public
      hologres foreign list --server odps_server
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    sql = """
        SELECT
            n.nspname AS schema,
            c.relname AS foreign_table,
            srv.srvname AS server,
            pg_catalog.pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_foreign_table ft
        JOIN pg_catalog.pg_class c ON c.oid = ft.ftrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_foreign_server srv ON srv.oid = ft.ftserver
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema',
                                'hologres', 'hg_internal')
    """
    params: list = []
    if schema_name:
        sql += " AND n.nspname = %s"
        params.append(schema_name)
    if server:
        sql += " AND srv.srvname = %s"
        params.append(server)
    sql += " ORDER BY n.nspname, c.relname"

    try:
        rows = conn.execute(sql, tuple(params))
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.list", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, row_count=len(rows), duration_ms=duration_ms)
        print_output(success_rows(rows, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.list", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# foreign show
# ---------------------------------------------------------------------------
@foreign_cmd.command("show")
@click.argument("name")
@click.pass_context
def show_cmd(ctx: click.Context, name: str) -> None:
    """Show foreign table structure: server, options, columns.

    NAME: '[schema.]foreign_table'.

    \b
    Examples:
      hologres foreign show src_pt
      hologres foreign show public.src_pt
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    schema_name, table_name = _split_schema_qualified(name)
    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "foreign table name")
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
        return

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        meta_sql = """
            SELECT
                srv.srvname AS server,
                ft.ftoptions AS options,
                pg_catalog.pg_get_userbyid(c.relowner) AS owner
            FROM pg_catalog.pg_foreign_table ft
            JOIN pg_catalog.pg_class c ON c.oid = ft.ftrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_foreign_server srv ON srv.oid = ft.ftserver
            WHERE n.nspname = %s AND c.relname = %s
        """
        meta_rows = conn.execute(meta_sql, (schema_name, table_name))
        if not meta_rows:
            print_output(error("FOREIGN_TABLE_NOT_FOUND",
                               f"Foreign table '{schema_name}.{table_name}' not found",
                               fmt))
            return

        meta = meta_rows[0]
        # ftoptions is a text[] of "key=value"; parse into a dict for readability.
        raw_options = meta.get("options") or []
        options: dict[str, str] = {}
        for opt in raw_options:
            if "=" in opt:
                k, v = opt.split("=", 1)
                options[k] = v
            else:
                options[opt] = ""

        columns_sql = """
            SELECT column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        columns = conn.execute(columns_sql, (schema_name, table_name))

        result = {
            "schema": schema_name,
            "foreign_table": table_name,
            "server": meta.get("server"),
            "owner": meta.get("owner"),
            "options": options,
            "columns": columns,
        }

        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.show", sql=f"SHOW {schema_name}.{table_name}",
                      dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(columns), duration_ms=duration_ms)

        if fmt == FORMAT_JSON:
            print_output(success(result))
        else:
            print_output(success_rows(columns, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.show", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e),
                      duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# foreign create
# ---------------------------------------------------------------------------
@foreign_cmd.command("create")
@click.option("--name", "-n", required=True,
              help="Foreign table name [schema.]table_name (required).")
@click.option("--columns", "-c", required=True,
              help='Column definitions. Example: "id text, pt text"')
@click.option("--server", default=DEFAULT_SERVER, show_default=True,
              help="Foreign server name (e.g. odps_server / paimon_server).")
@click.option("--project-name", required=True,
              help="MaxCompute project name (or DLF metadata-database name).")
@click.option("--odps-schema", default=None,
              help="MaxCompute schema name for three-layer model. "
                   "When set, project_name becomes 'project#schema'.")
@click.option("--odps-table", "odps_table_name", default=None,
              help="Remote table_name. Defaults to the local foreign table name.")
@click.option("--option", "extra_options", multiple=True,
              help='Additional OPTIONS as "key=value". Repeatable.')
@click.option("--if-not-exists", is_flag=True, default=False,
              help="Add IF NOT EXISTS clause.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing.")
@click.pass_context
def create_cmd(ctx: click.Context, name: str, columns: str, server: str,
               project_name: str, odps_schema: Optional[str],
               odps_table_name: Optional[str],
               extra_options: Tuple[str, ...],
               if_not_exists: bool, dry_run: bool) -> None:
    """Create a foreign table.

    \b
    Examples:
      # MaxCompute two-layer model
      hologres foreign create -n public.src_pt \\
        -c "id text, pt text" \\
        --project-name my_odps_project --odps-table src_pt --dry-run

    \b
      # MaxCompute three-layer model (project + schema)
      hologres foreign create -n public.region \\
        -c "r_regionkey bigint, r_name text" \\
        --project-name odps_hologres --odps-schema tpch_10g \\
        --odps-table odps_region_10g --dry-run

    \b
      # DLF Paimon (custom server)
      hologres foreign create -n public.events \\
        -c "id bigint, ts timestamptz" \\
        --server paimon_server --project-name github_events \\
        --odps-table events --dry-run
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    schema_name, table_name = _split_schema_qualified(name)
    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "foreign table name")
        _validate_identifier(server, "server name")
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
        return

    extras: dict[str, str] = {}
    for raw in extra_options:
        if "=" not in raw:
            print_output(error(ErrorCode.INVALID_ARGS,
                               f'Invalid --option "{raw}". Expected "key=value".', fmt))
            return
        key, value = raw.split("=", 1)
        extras[key.strip()] = value.strip()

    sql = _build_foreign_create_sql(
        schema_name=schema_name,
        table_name=table_name,
        columns=columns,
        server=server,
        project_name=project_name,
        odps_schema=odps_schema,
        odps_table_name=odps_table_name,
        if_not_exists=if_not_exists,
        extra_options=extras or None,
    )

    if dry_run:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode)"))
        return

    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.create", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Foreign table created successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.create", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# foreign alter
# ---------------------------------------------------------------------------
@foreign_cmd.command("alter")
@click.argument("name")
@click.option("--add-column", multiple=True,
              help='Add a column. Format: "name TYPE". Repeatable.')
@click.option("--drop-column", multiple=True,
              help="Drop a column by name. Repeatable.")
@click.option("--rename", default=None,
              help="Rename the foreign table to a new name (without schema).")
@click.option("--no-if-exists", is_flag=True, default=False,
              help="Omit IF EXISTS from generated ALTER statements.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing.")
@click.pass_context
def alter_cmd(ctx: click.Context, name: str,
              add_column: Tuple[str, ...],
              drop_column: Tuple[str, ...],
              rename: Optional[str],
              no_if_exists: bool, dry_run: bool) -> None:
    """Alter a foreign table: add/drop columns or rename.

    \b
    NAME: Foreign table name in format [schema.]name.

    \b
    Examples:
      hologres foreign alter public.bank --add-column "score float8"
      hologres foreign alter public.bank --drop-column score --dry-run
      hologres foreign alter public.bank --rename bank_v2 --dry-run
      hologres foreign alter public.bank \\
        --add-column "a float8" --add-column "b float8" --dry-run
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    schema_name, table_name = _split_schema_qualified(name)
    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "foreign table name")
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
        return

    if rename is not None:
        try:
            _validate_identifier(rename, "new foreign table name")
        except ValueError as e:
            print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
            return

    for col in drop_column:
        try:
            _validate_identifier(col.strip(), "column name")
        except ValueError as e:
            print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
            return

    sql = _build_foreign_alter_sql(
        schema_name=schema_name,
        table_name=table_name,
        add_columns=add_column,
        drop_columns=drop_column,
        rename=rename,
        if_exists=not no_if_exists,
    )

    if not sql:
        print_output(error(ErrorCode.NO_CHANGES,
                           "No changes specified. Use --add-column / --drop-column / --rename.",
                           fmt))
        return

    if dry_run:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode)"))
        return

    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.alter", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Foreign table altered successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.alter", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# foreign drop
# ---------------------------------------------------------------------------
@foreign_cmd.command("drop")
@click.argument("name")
@click.option("--if-exists", is_flag=True, default=False,
              help="Add IF EXISTS clause; no error if foreign table is missing.")
@click.option("--cascade", is_flag=True, default=False,
              help="Add CASCADE to drop dependent objects.")
@click.option("--restrict", is_flag=True, default=False,
              help="Add RESTRICT to refuse drop when dependents exist.")
@click.option("--confirm", is_flag=True, default=False,
              help="[REQUIRED to execute] Confirm the drop. "
                   "Without --confirm, only dry-run SQL is shown.")
@click.pass_context
def drop_cmd(ctx: click.Context, name: str, if_exists: bool,
             cascade: bool, restrict: bool, confirm: bool) -> None:
    """Drop a foreign table.

    \b
    NAME: Foreign table name in format [schema.]name.

    \b
    SAFETY: Destructive operation. By default only shows the SQL.
    Use --confirm to actually execute the DROP.

    \b
    Examples:
      hologres foreign drop public.src_pt                  # dry-run
      hologres foreign drop public.src_pt --confirm
      hologres foreign drop public.src_pt --if-exists --confirm
      hologres foreign drop public.src_pt --cascade --confirm
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if cascade and restrict:
        print_output(error(ErrorCode.INVALID_ARGS,
                           "--cascade and --restrict are mutually exclusive.", fmt))
        return

    schema_name, table_name = _split_schema_qualified(name)
    try:
        _validate_identifier(schema_name, "schema name")
        _validate_identifier(table_name, "foreign table name")
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
        return

    full_name = f"{schema_name}.{table_name}"
    parts = ["DROP FOREIGN TABLE"]
    if if_exists:
        parts.append("IF EXISTS")
    parts.append(full_name)
    if cascade:
        parts.append("CASCADE")
    elif restrict:
        parts.append("RESTRICT")
    sql = " ".join(parts) + ";"

    if not confirm:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode); pass --confirm to execute."))
        return

    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.drop", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Foreign table dropped successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.drop", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# foreign import (IMPORT FOREIGN SCHEMA)
# ---------------------------------------------------------------------------
@foreign_cmd.command("import")
@click.option("--remote-schema", required=True,
              help="Remote project / metadata-database name to import from. "
                   "For MaxCompute three-layer model, combine with --odps-schema.")
@click.option("--odps-schema", default=None,
              help="MaxCompute schema for three-layer model "
                   "(remote_schema becomes 'project#schema').")
@click.option("--server", default=DEFAULT_SERVER, show_default=True,
              help="Foreign server name (odps_server / paimon_server / ...).")
@click.option("--into", "into_schema", required=True,
              help="Local Hologres schema to import the tables into (e.g. public).")
@click.option("--limit-to", default=None,
              help="Comma-separated list of remote table names to import.")
@click.option("--except", "exclude", default=None,
              help="Comma-separated list of remote table names to exclude. "
                   "Mutually exclusive with --limit-to.")
@click.option("--if-table-exist",
              type=click.Choice(VALID_IF_TABLE_EXIST),
              default=None,
              help="Behavior when a target foreign table already exists "
                   "(default server-side: error).")
@click.option("--if-unsupported-type",
              type=click.Choice(VALID_IF_UNSUPPORTED_TYPE),
              default=None,
              help="Behavior on columns whose remote types are unsupported "
                   "(default server-side: skip).")
@click.option("--prefix", default=None,
              help="Prefix prepended to imported foreign table names "
                   "(Hologres V1.1.26+).")
@click.option("--suffix", default=None,
              help="Suffix appended to imported foreign table names "
                   "(Hologres V1.1.26+).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Only display the SQL without executing.")
@click.pass_context
def import_cmd(ctx: click.Context, remote_schema: str,
               odps_schema: Optional[str], server: str, into_schema: str,
               limit_to: Optional[str], exclude: Optional[str],
               if_table_exist: Optional[str],
               if_unsupported_type: Optional[str],
               prefix: Optional[str], suffix: Optional[str],
               dry_run: bool) -> None:
    """Batch-import foreign tables via IMPORT FOREIGN SCHEMA.

    \b
    Examples:
      # MaxCompute two-layer
      hologres foreign import \\
        --remote-schema public_data \\
        --limit-to customer,customer_address \\
        --into public --if-table-exist update --dry-run

    \b
      # MaxCompute three-layer
      hologres foreign import \\
        --remote-schema odps_hologres --odps-schema tpch_10g \\
        --limit-to odps_region_10g \\
        --into public --if-table-exist error \\
        --if-unsupported-type error --dry-run

    \b
      # DLF Paimon
      hologres foreign import \\
        --server paimon_server --remote-schema github_events \\
        --limit-to events --into public --if-table-exist update --dry-run
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if limit_to and exclude:
        print_output(error(ErrorCode.INVALID_ARGS,
                           "--limit-to and --except are mutually exclusive.", fmt))
        return

    try:
        _validate_identifier(into_schema, "into schema name")
        _validate_identifier(server, "server name")
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
        return

    limit_list: Tuple[str, ...] = tuple(
        t.strip() for t in (limit_to.split(",") if limit_to else []) if t.strip()
    )
    except_list: Tuple[str, ...] = tuple(
        t.strip() for t in (exclude.split(",") if exclude else []) if t.strip()
    )

    for col in (*limit_list, *except_list):
        try:
            _validate_identifier(col, "remote table name")
        except ValueError as e:
            print_output(error(ErrorCode.INVALID_INPUT, str(e), fmt))
            return

    try:
        sql = _build_import_foreign_schema_sql(
            remote_schema=remote_schema,
            odps_schema=odps_schema,
            server=server,
            into_schema=into_schema,
            limit_to=limit_list,
            exclude=except_list,
            if_table_exist=if_table_exist,
            if_unsupported_type=if_unsupported_type,
            prefix=prefix,
            suffix=suffix,
        )
    except ValueError as e:
        print_output(error(ErrorCode.INVALID_ARGS, str(e), fmt))
        return

    if dry_run:
        print_output(success({"sql": sql, "dry_run": True}, fmt,
                             message="SQL generated (dry-run mode)"))
        return

    try:
        conn = get_connection(profile=profile, read_only=False)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    start_time = time.time()
    try:
        conn.execute(sql)
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.import", sql=sql, dsn_masked=conn.masked_dsn,
                      success=True, duration_ms=duration_ms)
        print_output(success({"sql": sql, "executed": True}, fmt,
                             message="Foreign schema imported successfully"))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("foreign.import", sql=sql, dsn_masked=conn.masked_dsn,
                      success=False, error_code="QUERY_ERROR",
                      error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
