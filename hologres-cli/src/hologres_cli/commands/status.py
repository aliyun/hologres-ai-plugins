"""Status command for Hologres CLI."""

from __future__ import annotations

import time

import click

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import FORMAT_JSON, connection_error, print_output, query_error, success


@click.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Show connection status and server information."""
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        raw_version = conn.execute("SELECT hg_version()")[0]["hg_version"]
        # Extract short version like "Hologres 3.1.36" from full version string
        version = raw_version.split("(")[0].strip() if "(" in raw_version else raw_version
        database = conn.execute("SELECT current_database()")[0]["current_database"]
        user = conn.execute("SELECT current_user")[0]["current_user"]

        try:
            addr_result = conn.execute("SELECT inet_server_addr(), inet_server_port()")
            server_addr = addr_result[0].get("inet_server_addr", "N/A")
            server_port = addr_result[0].get("inet_server_port", "N/A")
        except Exception:
            server_addr = server_port = "N/A"

        duration_ms = (time.time() - start_time) * 1000
        log_operation("status", dsn_masked=conn.masked_dsn, success=True, duration_ms=duration_ms)

        result = {
            "status": "connected",
            "version": version,
            "database": database,
            "user": user,
            "server_address": str(server_addr),
            "server_port": str(server_port),
            "dsn": conn.masked_dsn,
        }
        print_output(success(result, fmt))
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("status", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
