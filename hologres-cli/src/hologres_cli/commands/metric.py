"""Cloud monitoring metric commands for Hologres CLI."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import click

from .. import credentials
from ..config_store import get_current_profile, set_profile
from ..logger import log_operation
from ..output import FORMAT_JSON, error, print_output, success, success_rows

NAMESPACE = "acs_hologres"


def _resolve_region(region_cli: str | None) -> str:
    """Return *region_cli* when given, else fall back to the active profile's
    ``region_id``, and finally to ``"cn-hangzhou"``."""
    if region_cli:
        return region_cli
    try:
        profile = get_current_profile()
        rid = profile.get("region_id")
        if rid:
            return rid
    except Exception:
        pass
    return "cn-hangzhou"


@click.group("metric")
@click.pass_context
def metric_cmd(ctx: click.Context) -> None:
    """Cloud monitoring metric commands for Hologres instances."""
    pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _import_cms_sdk() -> Tuple[Any, Any, Any, Any, Any]:
    """Lazy-import the CloudMonitor SDK. Raises ImportError on failure."""
    from alibabacloud_cms20190101.client import Client as CMSClient
    from alibabacloud_cms20190101 import models as cms_models
    from alibabacloud_credentials.client import Client as CredentialClient
    from alibabacloud_credentials.models import Config as CredentialConfig
    from alibabacloud_tea_openapi.models import Config
    return CMSClient, cms_models, CredentialClient, CredentialConfig, Config


def _resolve_ak_credential_client(profile: dict) -> Any:
    """Resolve a non-STS credential client via the legacy 3-tier priority.

    Kept unchanged for backward compatibility with ``ram``/``basic`` profiles:

    1. metric-specific AK/SK (``cms_access_key_id`` / ``cms_access_key_secret``)
    2. general AK/SK (``access_key_id`` / ``access_key_secret``)
    3. ``CredentialClient()`` default chain (env vars, ``~/.aliyun/config.json``,
       instance RAM role, ...).
    """
    _, _, CredentialClient, CredentialConfig, _ = _import_cms_sdk()

    ak = profile.get("cms_access_key_id")
    sk = profile.get("cms_access_key_secret")
    if not (ak and sk):
        ak = profile.get("access_key_id")
        sk = profile.get("access_key_secret")
    if ak and sk:
        return CredentialClient(CredentialConfig(
            type="access_key",
            access_key_id=ak,
            access_key_secret=sk,
        ))
    return CredentialClient()


def _create_cms_client(region: str) -> Any:
    """Create a CloudMonitor client.

    Credentials are resolved by the profile's ``auth_mode``:

    - ``sts``: reuse the SQL-link credential resolver
      (:func:`credentials.get_credential_client`) — honors ``credentials_uri``
      (explicit provider) or the default chain (standard STS env vars /
      ``ALIBABA_CLOUD_CREDENTIALS_URI`` / ECS metadata), with in-process
      auto-refresh of session tokens. Identical to the SQL/OpenAPI path.
    - otherwise (``ram``/``basic``): legacy 3-tier priority via
      :func:`_resolve_ak_credential_client` (cms AK → general AK → default chain).
    """
    CMSClient, _, _, _, Config = _import_cms_sdk()

    try:
        profile = get_current_profile()
    except Exception:
        profile = {}

    if profile.get("auth_mode") == "sts":
        credential_client = credentials.get_credential_client(profile)
    else:
        credential_client = _resolve_ak_credential_client(profile)

    config = Config(credential=credential_client, region_id=region)
    config.endpoint = f"metrics.{region}.aliyuncs.com"
    return CMSClient(config)


def _dependency_missing_error(fmt: str) -> None:
    print_output(error(
        "DEPENDENCY_MISSING",
        "alibabacloud_cms20190101, alibabacloud-credentials, and "
        "alibabacloud-tea-openapi packages are required. "
        "Install with: pip install 'hologres-cli[cms]' or "
        "pip install alibabacloud_cms20190101 alibabacloud-credentials alibabacloud-tea-openapi",
        fmt,
    ))


def _credential_error(fmt: str, exc: Exception) -> None:
    print_output(error(
        "CREDENTIAL_ERROR",
        f"Failed to initialize CloudMonitor client. "
        f"Please configure AK/SK via `hologres metric config` (recommended) "
        f"or `hologres config` (general AK/SK), "
        f"or set environment variables "
        f"(ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET), "
        f"or use an instance RAM role. Detail: {exc}",
        fmt,
    ))


def _init_cms_client(fmt: str, region: str, op_start: float, op_name: str) -> Any:
    """Create the CMS client, mapping credential errors to structured output.

    Returns the client, or ``None`` after printing an error (caller should return).

    STS failures surface their precise ``CredentialsError`` code (e.g.
    ``STS_FETCH_ERROR`` with retryable/hint); other init failures fall back to
    the generic ``CREDENTIAL_ERROR`` hint via :func:`_credential_error`.
    """
    try:
        return _create_cms_client(region)
    except credentials.CredentialsError as exc:
        log_operation(
            op_name, success=False, error_code=exc.code,
            error_message=str(exc), duration_ms=(time.time() - op_start) * 1000,
        )
        print_output(error(exc.code, str(exc), fmt))
        return None
    except Exception as exc:
        log_operation(
            op_name, success=False, error_code="CREDENTIAL_ERROR",
            error_message=str(exc), duration_ms=(time.time() - op_start) * 1000,
        )
        _credential_error(fmt, exc)
        return None


# ---------------------------------------------------------------------------
# metric config
# ---------------------------------------------------------------------------


@metric_cmd.command("config")
@click.option("--access-key-id", default=None, help="CloudMonitor Access Key ID")
@click.option("--access-key-secret", default=None, help="CloudMonitor Access Key Secret")
@click.option("--show", is_flag=True, default=False, help="Show current metric credentials (masked)")
@click.pass_context
def config_cmd(ctx: click.Context, access_key_id: str | None, access_key_secret: str | None, show: bool) -> None:
    """Configure CloudMonitor (CMS) credentials for metric commands.

    \b
    Allows setting a dedicated AK/SK for CloudMonitor metric queries,
    separate from the general Hologres connection credentials.

    \b
    Examples:
      hologres metric config                                  # interactive
      hologres metric config --access-key-id xxx --access-key-secret yyy
      hologres metric config --show                           # show masked
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)

    if show:
        try:
            profile = get_current_profile()
        except Exception:
            profile = {}
        cms_ak = profile.get("cms_access_key_id", "")
        cms_sk = profile.get("cms_access_key_secret", "")
        masked_ak = (
            cms_ak[:4] + "****" + cms_ak[-4:]
            if len(cms_ak) > 8
            else ("****" if cms_ak else "(not set)")
        )
        masked_sk = (
            cms_sk[:4] + "****" + cms_sk[-4:]
            if len(cms_sk) > 8
            else ("****" if cms_sk else "(not set)")
        )
        print_output(
            success({"cms_access_key_id": masked_ak, "cms_access_key_secret": masked_sk}, fmt)
        )
        return

    # Interactive prompts when arguments are not provided
    if not access_key_id:
        access_key_id = click.prompt("CloudMonitor Access Key ID")
    if not access_key_secret:
        access_key_secret = click.prompt("CloudMonitor Access Key Secret", hide_input=True)

    try:
        profile = get_current_profile()
    except Exception:
        print_output(error(
            "CONFIG_ERROR",
            "No current profile configured. "
            "Run 'hologres config' to set up your first profile before "
            "configuring metric credentials.",
            fmt,
        ))
        return

    profile["cms_access_key_id"] = access_key_id
    profile["cms_access_key_secret"] = access_key_secret
    set_profile(profile)

    print_output(success({"message": "CloudMonitor credentials saved successfully."}, fmt))


# ---------------------------------------------------------------------------
# metric list (DescribeMetricMetaList)
# ---------------------------------------------------------------------------


@metric_cmd.command("list")
@click.option("--search", default=None,
              help="Filter metrics by keyword (fuzzy match on metric_name and description)")
@click.option("--region", default=None,
              help="CloudMonitor region (defaults to config profile region_id, then cn-hangzhou)")
@click.option("--page-size", default=100, show_default=True, type=int,
              help="Page size when fetching metric metadata (max 100)")
@click.pass_context
def list_cmd(ctx: click.Context, search: str | None, region: str | None, page_size: int) -> None:
    """List available Hologres monitoring metrics via DescribeMetricMetaList API.

    \b
    Queries the acs_hologres namespace and returns all metric metadata
    (metric_name, description, unit, dimensions, periods, statistics).

    \b
    Requires Alibaba Cloud credentials. Resolution order (high to low):
      1) `hologres metric config` (CloudMonitor-dedicated AK/SK, recommended)
      2) `hologres config` (general AK/SK in ~/.hologres/config.json)
      3) Environment variables (ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET)
         or other providers supported by alibabacloud-credentials
         (e.g. instance RAM role).

    \b
    Examples:
      hologres metric list
      hologres metric list --search cpu
      hologres metric list --search 延迟
      hologres -f table metric list
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    region = _resolve_region(region)
    op_start = time.time()

    try:
        _, cms_models, _, _, _ = _import_cms_sdk()
        DescribeMetricMetaListRequest = cms_models.DescribeMetricMetaListRequest
    except ImportError:
        _dependency_missing_error(fmt)
        return

    client = _init_cms_client(fmt, region, op_start, "metric.list")
    if client is None:
        return

    rows: list[dict[str, Any]] = []
    page_number = 1

    try:
        while True:
            request = DescribeMetricMetaListRequest(
                namespace=NAMESPACE,
                page_number=page_number,
                page_size=page_size,
            )
            response = client.describe_metric_meta_list(request)
            body = response.body

            if body.code and str(body.code) != "200":
                duration_ms = (time.time() - op_start) * 1000
                log_operation(
                    "metric.list",
                    success=False,
                    error_code=str(body.code),
                    error_message=getattr(body, "message", "") or "",
                    duration_ms=duration_ms,
                )
                print_output(error(
                    "API_ERROR",
                    f"CloudMonitor API error: code={body.code}, "
                    f"message={getattr(body, 'message', '')}",
                    fmt,
                ))
                return

            resources = []
            if body.resources and getattr(body.resources, "resource", None):
                resources = body.resources.resource

            for r in resources:
                rows.append({
                    "metric_name": getattr(r, "metric_name", "") or "",
                    "description": getattr(r, "description", "") or "",
                    "unit": getattr(r, "unit", "") or "",
                    "dimensions": getattr(r, "dimensions", "") or "",
                    "periods": getattr(r, "periods", "") or "",
                    "statistics": getattr(r, "statistics", "") or "",
                })

            # Pagination: stop when collected enough or no more results
            try:
                total = int(body.total_count) if body.total_count is not None else len(rows)
            except (TypeError, ValueError):
                total = len(rows)

            if not resources or len(rows) >= total:
                break
            page_number += 1

    except Exception as exc:
        duration_ms = (time.time() - op_start) * 1000
        log_operation(
            "metric.list",
            success=False,
            error_code="API_ERROR",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        print_output(error("API_ERROR", f"CloudMonitor API call failed: {exc}", fmt))
        return

    # Client-side fuzzy filter
    if search:
        needle = search.lower()
        rows = [
            r for r in rows
            if needle in r["metric_name"].lower()
            or needle in r["description"].lower()
        ]

    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        "metric.list",
        success=True,
        row_count=len(rows),
        duration_ms=duration_ms,
        extra={"region": region, "search": search},
    )
    print_output(success_rows(rows, fmt))


# ---------------------------------------------------------------------------
# metric query (DescribeMetricList)
# ---------------------------------------------------------------------------


def _parse_timestamp(value: str) -> str:
    """Accept an ISO-8601 string or millisecond timestamp and return ms string."""
    try:
        ms = int(value)
        return str(ms)
    except ValueError:
        pass
    # Try ISO-8601 parsing
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp() * 1000))


def _default_start_ms() -> str:
    """Return millisecond timestamp for 1 hour ago."""
    return str(int((time.time() - 3600) * 1000))


def _default_end_ms() -> str:
    """Return millisecond timestamp for now."""
    return str(int(time.time() * 1000))


def _build_dimensions(instance_id: str, dimensions_json: str | None,
                      fmt: str) -> Optional[str]:
    """Merge --dimensions JSON with instanceId. Returns serialized JSON or None on error."""
    dims: dict[str, str] = {}
    if dimensions_json:
        try:
            dims = json.loads(dimensions_json)
        except json.JSONDecodeError as exc:
            print_output(error("INVALID_INPUT", f"--dimensions must be valid JSON: {exc}", fmt))
            return None
    dims["instanceId"] = instance_id
    return json.dumps([dims], ensure_ascii=False)


@metric_cmd.command("query")
@click.argument("metric_name")
@click.option("--instance-id", required=True, help="Hologres instance ID")
@click.option("--start-time", "start_time", default=None,
              help="Start time (ISO-8601 or epoch ms). Default: 1 hour ago")
@click.option("--end-time", "end_time", default=None,
              help="End time (ISO-8601 or epoch ms). Default: now")
@click.option("--period", default=60, type=int, show_default=True,
              help="Data aggregation period in seconds (e.g. 60, 300)")
@click.option("--dimensions", "dimensions_json", default=None,
              help="Extra dimensions as JSON string (instanceId is auto-injected)")
@click.option("--region", default=None,
              help="CloudMonitor region (defaults to config profile region_id, then cn-hangzhou)")
@click.pass_context
def query_cmd(
    ctx: click.Context,
    metric_name: str,
    instance_id: str,
    start_time: str | None,
    end_time: str | None,
    period: int,
    dimensions_json: str | None,
    region: str | None,
) -> None:
    """Query monitoring metric data from Alibaba Cloud CloudMonitor.

    \b
    METRIC_NAME: The metric to query (see `hologres metric list`).
    Metric names include a product type prefix:
      standard_  (Standard instance)
      warehouse_ (Warehouse/compute group)
      follower_  (Read replica)
      serverless_ (Serverless)
      shared_    (Lake acceleration)

    \b
    Requires Alibaba Cloud credentials. Resolution order (high to low):
      1) `hologres metric config` (CloudMonitor-dedicated AK/SK, recommended)
      2) `hologres config` (general AK/SK in ~/.hologres/config.json)
      3) Environment variables (ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET)
         or other providers supported by alibabacloud-credentials
         (e.g. instance RAM role).

    \b
    Examples:
      hologres metric query standard_cpu_usage --instance-id hgprecn-cn-xxx
      hologres metric query warehouse_memory_usage --instance-id hgprecn-cn-xxx --period 300
      hologres metric query standard_query_qps --instance-id hgprecn-cn-xxx \\
          --start-time 2025-01-01T00:00:00 --end-time 2025-01-01T01:00:00 --dimensions '{"cmdType": "select"}'
      hologres -f table metric query standard_connections --instance-id hgprecn-cn-xxx
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    region = _resolve_region(region)
    op_start = time.time()

    # Resolve time range
    try:
        start_ms = _parse_timestamp(start_time) if start_time else _default_start_ms()
        end_ms = _parse_timestamp(end_time) if end_time else _default_end_ms()
    except Exception as exc:
        print_output(error("INVALID_INPUT", f"Invalid time format: {exc}", fmt))
        return

    dims_str = _build_dimensions(instance_id, dimensions_json, fmt)
    if dims_str is None:
        return

    try:
        _, cms_models, _, _, _ = _import_cms_sdk()
        DescribeMetricListRequest = cms_models.DescribeMetricListRequest
    except ImportError:
        _dependency_missing_error(fmt)
        return

    client = _init_cms_client(fmt, region, op_start, "metric.query")
    if client is None:
        return

    # Paginated fetch
    all_datapoints: list[dict[str, Any]] = []
    next_token: str | None = None

    try:
        while True:
            request = DescribeMetricListRequest(
                namespace=NAMESPACE,
                metric_name=metric_name,
                start_time=start_ms,
                end_time=end_ms,
                period=str(period),
                dimensions=dims_str,
            )
            if next_token:
                request.next_token = next_token

            response = client.describe_metric_list(request)
            body = response.body

            if body.code and str(body.code) != "200":
                duration_ms = (time.time() - op_start) * 1000
                log_operation(
                    "metric.query",
                    success=False,
                    error_code=str(body.code),
                    error_message=body.message or "",
                    duration_ms=duration_ms,
                )
                print_output(error(
                    "API_ERROR",
                    f"CloudMonitor API error: code={body.code}, message={body.message}",
                    fmt,
                ))
                return

            # Datapoints is a JSON string
            if body.datapoints:
                points = json.loads(body.datapoints)
                all_datapoints.extend(points)

            next_token = body.next_token
            if not next_token:
                break

        duration_ms = (time.time() - op_start) * 1000
        log_operation(
            "metric.query",
            success=True,
            row_count=len(all_datapoints),
            duration_ms=duration_ms,
            extra={"metric_name": metric_name, "instance_id": instance_id, "region": region},
        )
        print_output(success_rows(all_datapoints, fmt))

    except Exception as exc:
        duration_ms = (time.time() - op_start) * 1000
        log_operation(
            "metric.query",
            success=False,
            error_code="API_ERROR",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        print_output(error("API_ERROR", f"CloudMonitor API call failed: {exc}", fmt))


# ---------------------------------------------------------------------------
# metric latest (DescribeMetricLast)
# ---------------------------------------------------------------------------


@metric_cmd.command("latest")
@click.argument("metric_name")
@click.option("--instance-id", required=True, help="Hologres instance ID")
@click.option("--period", default=None, type=int,
              help="Data aggregation period in seconds (e.g. 60, 300). Default: API default")
@click.option("--dimensions", "dimensions_json", default=None,
              help="Extra dimensions as JSON string (instanceId is auto-injected)")
@click.option("--region", default=None,
              help="CloudMonitor region (defaults to config profile region_id, then cn-hangzhou)")
@click.pass_context
def latest_cmd(
    ctx: click.Context,
    metric_name: str,
    instance_id: str,
    period: int | None,
    dimensions_json: str | None,
    region: str | None,
) -> None:
    """Fetch the latest datapoint of a metric via DescribeMetricLast API.

    \b
    METRIC_NAME: The metric to query (see `hologres metric list`).
    Metric names include a product type prefix:
      standard_  (Standard instance)
      warehouse_ (Warehouse instance)
      follower_  (Follower instance)
      serverless_ (Serverless instance)
      shared_    (Lake acceleration)

    \b
    Unlike `metric query` which returns a time series, `metric latest`
    returns the most recent datapoint(s) for quick health checks.

    \b
    Requires Alibaba Cloud credentials. Resolution order (high to low):
      1) `hologres metric config` (CloudMonitor-dedicated AK/SK, recommended)
      2) `hologres config` (general AK/SK in ~/.hologres/config.json)
      3) Environment variables (ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET)
         or other providers supported by alibabacloud-credentials
         (e.g. instance RAM role).

    \b
    Examples:
      hologres metric latest standard_cpu_usage --instance-id hgprecn-cn-xxx
      hologres metric latest warehouse_memory_usage --instance-id hgprecn-cn-xxx --period 60
      hologres -f table metric latest standard_connections --instance-id hgprecn-cn-xxx
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    region = _resolve_region(region)
    op_start = time.time()

    dims_str = _build_dimensions(instance_id, dimensions_json, fmt)
    if dims_str is None:
        return

    try:
        _, cms_models, _, _, _ = _import_cms_sdk()
        DescribeMetricLastRequest = cms_models.DescribeMetricLastRequest
    except ImportError:
        _dependency_missing_error(fmt)
        return

    client = _init_cms_client(fmt, region, op_start, "metric.latest")
    if client is None:
        return

    all_datapoints: list[dict[str, Any]] = []
    next_token: str | None = None

    try:
        while True:
            request_kwargs: dict[str, Any] = {
                "namespace": NAMESPACE,
                "metric_name": metric_name,
                "dimensions": dims_str,
            }
            if period is not None:
                request_kwargs["period"] = str(period)
            request = DescribeMetricLastRequest(**request_kwargs)
            if next_token:
                request.next_token = next_token

            response = client.describe_metric_last(request)
            body = response.body

            if body.code and str(body.code) != "200":
                duration_ms = (time.time() - op_start) * 1000
                log_operation(
                    "metric.latest",
                    success=False,
                    error_code=str(body.code),
                    error_message=getattr(body, "message", "") or "",
                    duration_ms=duration_ms,
                )
                print_output(error(
                    "API_ERROR",
                    f"CloudMonitor API error: code={body.code}, "
                    f"message={getattr(body, 'message', '')}",
                    fmt,
                ))
                return

            if body.datapoints:
                points = json.loads(body.datapoints)
                all_datapoints.extend(points)

            next_token = getattr(body, "next_token", None)
            if not next_token:
                break

        duration_ms = (time.time() - op_start) * 1000
        log_operation(
            "metric.latest",
            success=True,
            row_count=len(all_datapoints),
            duration_ms=duration_ms,
            extra={"metric_name": metric_name, "instance_id": instance_id, "region": region},
        )
        print_output(success_rows(all_datapoints, fmt))

    except Exception as exc:
        duration_ms = (time.time() - op_start) * 1000
        log_operation(
            "metric.latest",
            success=False,
            error_code="API_ERROR",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        print_output(error("API_ERROR", f"CloudMonitor API call failed: {exc}", fmt))
