"""Hologres CLI - Main entry point."""

from __future__ import annotations

import sys
from typing import Optional

import click

from . import __version__
from .connection import DSNError
from .output import FORMAT_JSON, VALID_FORMATS, error, print_output, success


@click.group()
@click.option("--profile", "-p", default=None, help="Use named profile from config")
@click.option("--format", "-f", type=click.Choice(VALID_FORMATS), default=FORMAT_JSON, help="Output format")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx: click.Context, profile: Optional[str], format: str) -> None:
    """Hologres CLI - AI-agent-friendly database interface.

    \b
    Connection: hologres config  |  --profile to switch
    """
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    ctx.obj["format"] = format



from .commands import schema, sql, data, status, instance, warehouse, dt, config, table, view, extension, guc  # noqa: E402
cli.add_command(schema.schema_cmd)
cli.add_command(sql.sql_cmd)
cli.add_command(data.data_cmd)
cli.add_command(status.status_cmd)
cli.add_command(instance.instance_cmd)
cli.add_command(warehouse.warehouse_cmd)
cli.add_command(dt.dt_cmd)
cli.add_command(config.config_cmd)
cli.add_command(table.table_cmd)
cli.add_command(view.view_cmd)
cli.add_command(extension.extension_cmd)
cli.add_command(guc.guc_cmd)


@cli.command("ai-guide")
@click.pass_context
def ai_guide_cmd(ctx: click.Context) -> None:
    """Generate AI agent guide for this CLI."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    guide = _generate_ai_guide()
    if fmt == FORMAT_JSON:
        print_output(success({"guide": guide}))
    else:
        print_output(guide)


def _generate_ai_guide() -> str:
    return """# Hologres CLI - AI Agent Guide

## Connection
Run `hologres config` to set up connection profile.
Use `--profile <name>` to switch profiles.

## Commands
- `hologres config` - Configure connection profiles
- `hologres table list` - List tables (with optional --schema filter)
- `hologres schema tables` - List tables
- `hologres schema describe <table>` - Describe table
- `hologres schema dump` - Export DDL
- `hologres table dump <schema.table>` - Export DDL for a table
- `hologres table show <table>` - Show table structure
- `hologres sql run "<query>"` - Execute SQL (read-only by default)
- `hologres sql run --write "<query>"` - Execute write SQL
- `hologres extension list` - List installed extensions
- `hologres extension create <name>` - Create an extension
- `hologres guc show <param>` - Show GUC parameter value
- `hologres guc set <param> <value>` - Set GUC parameter (database level, persistent)
- `hologres data export <table> -f <file>` - Export to CSV
- `hologres data import <table> -f <file>` - Import from CSV
- `hologres data count <table>` - Count rows
- `hologres status` - Connection status

## Safety: LIMIT required for >100 rows, --write for mutations, no DELETE/UPDATE without WHERE.
## Output: --format json|table|csv|jsonl. Default: json with {ok: true/false}.
"""


@cli.command("history")
@click.option("--count", "-n", default=20, help="Number of entries")
@click.pass_context
def history_cmd(ctx: click.Context, count: int) -> None:
    """Show recent command history."""
    from .logger import read_recent_logs
    from .output import success_rows
    fmt = ctx.obj.get("format", FORMAT_JSON)
    entries = read_recent_logs(count)
    print_output(success_rows(entries, fmt))


def main() -> None:
    try:
        cli(obj={})
    except DSNError as e:
        print_output(error("CONNECTION_ERROR", str(e)))
        sys.exit(1)
    except Exception as e:
        print_output(error("INTERNAL_ERROR", str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
