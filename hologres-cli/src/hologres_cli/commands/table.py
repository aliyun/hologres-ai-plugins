"""Table management commands for Hologres CLI."""

from __future__ import annotations

from typing import Optional

import click

from ..output import FORMAT_JSON
from .schema import _dump_table_ddl, _list_tables


@click.group("table")
def table_cmd() -> None:
    """Table management commands."""
    pass


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
    _dump_table_ddl(ctx.obj.get("dsn"), table, ctx.obj.get("format", FORMAT_JSON),
                    operation="table.dump")


@table_cmd.command("list")
@click.option("--schema", "-s", "schema_name", default=None, help="Filter by schema name")
@click.pass_context
def list_cmd(ctx: click.Context, schema_name: Optional[str]) -> None:
    """List all tables in the database (excluding system schemas)."""
    _list_tables(ctx.obj.get("dsn"), schema_name, ctx.obj.get("format", FORMAT_JSON),
                 operation="table.list")
