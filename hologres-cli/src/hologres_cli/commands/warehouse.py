"""Warehouse (计算组) information command for Hologres CLI."""

from __future__ import annotations

import time
from typing import Optional

import click

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..output import (
    FORMAT_JSON,
    connection_error,
    print_output,
    query_error,
    success,
    success_rows,
)


@click.command("warehouse")
@click.argument("warehouse_name", required=False, default=None)
@click.pass_context
def warehouse_cmd(ctx: click.Context, warehouse_name: Optional[str]) -> None:
    """Query Hologres warehouse (计算组) information.

    Lists all warehouses or filters by warehouse_name if provided.

    \b
    Fields returned:
      - warehouse_id: Unique warehouse ID
      - warehouse_name: Warehouse name
      - cpu: CPU cores
      - mem: Memory in GB
      - cluster_min_count: Min shard count
      - cluster_max_count: Max shard count
      - target_status: Target status (1=running, 2=stopped)
      - status: Current status (0=init, 1=running, 2=stopped, 3=failed, 4=processing)
      - status_detail: Status details
      - is_default: Whether default warehouse
      - config: Warehouse config
      - comment: Comments

    \b
    Examples:
      hologres warehouse                    # List all warehouses
      hologres warehouse init_warehouse     # Query specific warehouse
      hologres -f table warehouse           # List in table format
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
        if warehouse_name:
            sql = "SELECT * FROM hologres.hg_warehouses WHERE warehouse_name = %s"
            rows = conn.execute(sql, (warehouse_name,))
        else:
            sql = "SELECT * FROM hologres.hg_warehouses"
            rows = conn.execute(sql)

        duration_ms = (time.time() - start_time) * 1000
        log_operation("warehouse", sql=sql, dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows), duration_ms=duration_ms,
                      extra={"warehouse_name": warehouse_name} if warehouse_name else None)

        # Map status codes to human-readable descriptions
        status_map = {
            0: "initializing",
            1: "running",
            2: "stopped",
            3: "failed",
            4: "processing",
        }
        target_status_map = {
            1: "running",
            2: "stopped",
        }

        # Enrich rows with status descriptions
        enriched_rows = []
        for row in rows:
            enriched = dict(row)
            if "status" in enriched and enriched["status"] in status_map:
                enriched["status_desc"] = status_map[enriched["status"]]
            if "target_status" in enriched and enriched["target_status"] in target_status_map:
                enriched["target_status_desc"] = target_status_map[enriched["target_status"]]
            enriched_rows.append(enriched)

        print_output(success_rows(enriched_rows, fmt))

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("warehouse", dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        print_output(query_error(str(e), fmt))
    finally:
        conn.close()
