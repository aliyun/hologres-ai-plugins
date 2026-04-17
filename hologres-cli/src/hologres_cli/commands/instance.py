"""Instance information command for Hologres CLI."""

from __future__ import annotations

import time

import click

from ..connection import DSNError, HologresConnection, resolve_instance_dsn
from ..logger import log_operation
from ..output import FORMAT_JSON, connection_error, print_output, query_error, success


@click.command("instance")
@click.argument("instance_name")
@click.pass_context
def instance_cmd(ctx: click.Context, instance_name: str) -> None:
    """Query Hologres instance information.

    Shows version and max connections for the given instance.
    The instance_name must have a matching HOLOGRES_DSN_<instance_name>
    configured in ~/.hologres/config.env or as an environment variable.

    \b
    Config example (~/.hologres/config.env):
      HOLOGRES_DSN_myinstance="hologres://user:pass@host:port/db"

    \b
    Examples:
      hologres instance hologres-public3
      hologres -f table instance my-instance
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    start_time = time.time()

    try:
        dsn = resolve_instance_dsn(instance_name)
        conn = HologresConnection(dsn)
    except DSNError as e:
        print_output(connection_error(str(e), fmt))
        return

    try:
        # Query instance version
        version_result = conn.execute("SELECT hg_version()")
        hg_version = version_result[0]["hg_version"] if version_result else "Unknown"

        # Query instance max connections
        max_conn_result = conn.execute("SELECT instance_max_connections()")
        max_connections = max_conn_result[0]["instance_max_connections"] if max_conn_result else "Unknown"

        duration_ms = (time.time() - start_time) * 1000
        log_operation("instance", dsn_masked=conn.masked_dsn, success=True,
                      duration_ms=duration_ms, extra={"instance": instance_name})

        result = {
            "instance": instance_name,
            "hg_version": hg_version,
            "max_connections": max_connections,
        }
        print_output(success(result, fmt))

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("instance", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms,
                      extra={"instance": instance_name})
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
