"""Table management commands for Hologres CLI."""

from __future__ import annotations

import click

from ..output import FORMAT_JSON
from .schema import _dump_table_ddl


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
