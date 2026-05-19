"""Hologres instance management commands backed by the Hologram OpenAPI SDK.

This module exposes the ``hologres instance-manage`` command group, which
wraps the Alibaba Cloud Hologram OpenAPI (``alibabacloud_hologram20220601``)
to provide instance management capabilities, allowing AI agents to manage
Hologres instances (list/get/create/delete/stop/resume/restart/rename/scale)
through the unified CLI output and audit-log pipeline.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import click

from ..config_store import ConfigError, get_current_profile, get_profile
from ..logger import log_operation
from ..output import FORMAT_JSON, error, print_output, success, success_rows


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


@click.group("instance-manage")
@click.pass_context
def instance_manage_cmd(ctx: click.Context) -> None:
    """Hologres instance management via the Hologram OpenAPI.

    Provides instance management operations (list/get/create/delete/
    stop/resume/restart/rename/scale) for Hologres instances.

    \b
    Sub-commands:
      list     List all Hologres instances under the account
      get      Get details of a single instance
      create   Create a new instance
      delete   Delete an instance
      stop     Stop a running instance
      resume   Resume a stopped instance
      restart  Restart an instance
      rename   Rename an instance
      scale    Scale an instance up or down

    Credentials are taken from the active profile's ``access_key_id`` and
    ``access_key_secret``. The API endpoint is derived from the profile's
    ``region_id``.
    """
    pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_profile(ctx: click.Context, fmt: str) -> Optional[dict[str, Any]]:
    """Return the active profile, or print a CONFIG_ERROR and return None."""
    profile_name = ctx.obj.get("profile") if ctx.obj else None
    try:
        if profile_name:
            return get_profile(profile_name)
        return get_current_profile()
    except ConfigError as exc:
        print_output(error("CONFIG_ERROR", str(exc), fmt))
        return None
    except Exception as exc:  # pragma: no cover - defensive
        print_output(error("CONFIG_ERROR", f"Failed to load profile: {exc}", fmt))
        return None


def _import_hologram_sdk():
    """Lazy-import the Hologram SDK. Raises ImportError on failure."""
    from alibabacloud_hologram20220601.client import Client as HologramClient
    from alibabacloud_hologram20220601 import models as hologram_models
    from alibabacloud_tea_openapi import models as open_api_models
    return HologramClient, hologram_models, open_api_models


def _create_hologram_client(profile: dict) -> Any:
    """Create a Hologram API client from the given profile."""
    HologramClient, _, open_api_models = _import_hologram_sdk()

    ak = profile.get("access_key_id") or ""
    sk = profile.get("access_key_secret") or ""
    if not ak or not sk:
        raise ValueError(
            "access_key_id / access_key_secret missing from profile. "
            "Run 'hologres config' to configure."
        )

    config = open_api_models.Config(
        access_key_id=ak,
        access_key_secret=sk,
    )
    region_id = profile.get("region_id") or "cn-hangzhou"
    config.endpoint = f"hologram.{region_id}.aliyuncs.com"
    config.read_timeout = 20000  # ms; avoid premature SDK timeouts
    return HologramClient(config)


def _dependency_missing_error(fmt: str) -> None:
    print_output(error(
        "DEPENDENCY_MISSING",
        "alibabacloud_hologram20220601 and alibabacloud-tea-openapi packages "
        "are required. Install with: "
        "pip install alibabacloud_hologram20220601 alibabacloud-tea-openapi",
        fmt,
    ))


def _credential_error(fmt: str, exc: Exception) -> None:
    print_output(error(
        "CREDENTIAL_ERROR",
        f"Failed to initialize Hologram client. "
        f"Configure AK/SK via 'hologres config'. Detail: {exc}",
        fmt,
    ))


def _resolve_instance_id(cli_value: Optional[str], profile: dict,
                         fmt: str, op: str) -> Optional[str]:
    """Return *cli_value* if given, else fall back to ``profile['instance_id']``.

    Logs and prints an INVALID_INPUT error and returns None when neither
    source provides an instance id.
    """
    iid = cli_value or profile.get("instance_id") or ""
    if not iid:
        log_operation(
            op,
            success=False,
            error_code="INVALID_INPUT",
            error_message="instance_id not provided and not set in profile",
        )
        print_output(error(
            "INVALID_INPUT",
            "--instance-id is required (or set instance_id in your profile via "
            "'hologres config').",
            fmt,
        ))
        return None
    return iid


def _to_dict(obj: Any) -> Any:
    """Best-effort conversion of an Alibaba Cloud SDK model object to a dict.

    Falls back to recursively walking ``__dict__`` so JSON serialization works
    even when ``to_map`` is unavailable.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    to_map = getattr(obj, "to_map", None)
    if callable(to_map):
        try:
            return _to_dict(to_map())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def _extract_body(response: Any) -> Any:
    """Return ``response.body`` as a dict, or the response itself if no body."""
    body = getattr(response, "body", response)
    return _to_dict(body)


def _handle_api_exception(op: str, exc: Exception, fmt: str,
                          op_start: float) -> None:
    """Log + render an API_ERROR for an SDK exception."""
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=False,
        error_code="API_ERROR",
        error_message=str(exc),
        duration_ms=duration_ms,
    )
    # Surface structured error info when the SDK raises TeaException
    details: Optional[dict[str, Any]] = None
    code = getattr(exc, "code", None)
    msg = getattr(exc, "message", None) or str(exc)
    if code:
        details = {"sdk_code": str(code)}
    print_output(error("API_ERROR", f"Hologram API call failed: {msg}", fmt, details))


# ---------------------------------------------------------------------------
# hologram list
# ---------------------------------------------------------------------------


@instance_manage_cmd.command("list")
@click.option("--resource-group-id", default=None,
              help="Filter by resource group ID (optional)")
@click.pass_context
def list_cmd(ctx: click.Context, resource_group_id: Optional[str]) -> None:
    """List all Hologres instances under the current account.

    \b
    Examples:
      hologres instance-manage list
      hologres instance-manage list --resource-group-id rg-xxx
      hologres -f table instance-manage list
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.list"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    try:
        _, hologram_models, _ = _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    try:
        request = hologram_models.ListInstancesRequest(
            resource_group_id=resource_group_id,
        )
        response = client.list_instances(request)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    rows: list[dict[str, Any]] = []
    if isinstance(body, dict):
        instance_list = body.get("instanceList") or body.get("instance_list") or []
        if isinstance(instance_list, list):
            for item in instance_list:
                if isinstance(item, dict):
                    rows.append(item)

    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        row_count=len(rows),
        duration_ms=duration_ms,
        extra={"resource_group_id": resource_group_id},
    )

    if rows:
        print_output(success_rows(rows, fmt))
    else:
        # Fall back to the full body so users still see RequestId / total count.
        print_output(success(body, fmt))


# ---------------------------------------------------------------------------
# hologram get
# ---------------------------------------------------------------------------


@instance_manage_cmd.command("get")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.pass_context
def get_cmd(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Show detailed information about a single Hologres instance.

    \b
    Examples:
      hologres instance-manage get
      hologres instance-manage get --instance-id hgprecn-cn-xxx
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.get"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    iid = _resolve_instance_id(instance_id, profile, fmt, op)
    if iid is None:
        return

    try:
        _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    try:
        response = client.get_instance(iid)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={"instance_id": iid},
    )
    print_output(success(body, fmt))


# ---------------------------------------------------------------------------
# hologram create
# ---------------------------------------------------------------------------


_INSTANCE_TYPES = ["Standard", "Warehouse", "Follower", "Shared", "Serverless"]
_CHARGE_TYPES = ["PostPaid", "PrePaid"]


@instance_manage_cmd.command("create")
@click.option("--instance-name", required=True, help="Display name for the new instance")
@click.option("--instance-type", required=True,
              type=click.Choice(_INSTANCE_TYPES, case_sensitive=False),
              help="Instance type")
@click.option("--charge-type", required=True,
              type=click.Choice(_CHARGE_TYPES, case_sensitive=False),
              help="Billing mode")
@click.option("--region-id", default=None,
              help="Target region (defaults to profile region_id)")
@click.option("--zone-id", required=True, help="Availability zone, e.g. cn-hangzhou-h")
@click.option("--vpc-id", required=True, help="VPC ID")
@click.option("--vswitch-id", required=True, help="VSwitch ID")
@click.option("--cpu", default=None, type=int, help="CPU cores")
@click.option("--storage-size", default=None, type=int, help="Storage size in GB")
@click.option("--gateway-count", default=None, type=int,
              help="Gateway node count (Warehouse type)")
@click.option("--leader-instance-id", default=None,
              help="Leader instance ID (Follower type)")
@click.option("--auto-pay/--no-auto-pay", default=True, show_default=True,
              help="Whether to automatically pay for prepaid orders")
@click.pass_context
def create_cmd(
    ctx: click.Context,
    instance_name: str,
    instance_type: str,
    charge_type: str,
    region_id: Optional[str],
    zone_id: str,
    vpc_id: str,
    vswitch_id: str,
    cpu: Optional[int],
    storage_size: Optional[int],
    gateway_count: Optional[int],
    leader_instance_id: Optional[str],
    auto_pay: bool,
) -> None:
    """Create a new Hologres instance.

    \b
    Examples:
      hologres instance-manage create \\
          --instance-name my-holo --instance-type Standard \\
          --charge-type PostPaid --zone-id cn-hangzhou-h \\
          --vpc-id vpc-xxx --vswitch-id vsw-xxx --cpu 32 --storage-size 100
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.create"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    region = region_id or profile.get("region_id") or "cn-hangzhou"

    try:
        _, hologram_models, _ = _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    request_kwargs: dict[str, Any] = {
        "region_id": region,
        "zone_id": zone_id,
        "vpc_id": vpc_id,
        "v_switch_id": vswitch_id,
        "instance_name": instance_name,
        "instance_type": instance_type,
        "charge_type": charge_type,
        "pricing_cycle": "Month",
        "auto_pay": auto_pay,
    }
    if cpu is not None:
        request_kwargs["cpu"] = cpu
    if storage_size is not None:
        request_kwargs["storage_size"] = storage_size
    if gateway_count is not None:
        request_kwargs["gateway_count"] = gateway_count
    if leader_instance_id:
        request_kwargs["leader_instance_id"] = leader_instance_id

    try:
        request = hologram_models.CreateInstanceRequest(**request_kwargs)
        response = client.create_instance(request)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={
            "instance_name": instance_name,
            "instance_type": instance_type,
            "charge_type": charge_type,
            "region_id": region,
        },
    )
    print_output(success(body, fmt))


# ---------------------------------------------------------------------------
# Lifecycle helpers (delete / stop / resume / restart)
# ---------------------------------------------------------------------------


def _simple_lifecycle(
    ctx: click.Context,
    op: str,
    instance_id: Optional[str],
    sdk_method_name: str,
    extra_request: Optional[Any] = None,
) -> None:
    """Shared implementation for stop/resume/restart/delete."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    iid = _resolve_instance_id(instance_id, profile, fmt, op)
    if iid is None:
        return

    try:
        _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    try:
        method = getattr(client, sdk_method_name)
        if extra_request is not None:
            response = method(iid, extra_request)
        else:
            response = method(iid)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={"instance_id": iid},
    )
    print_output(success(body, fmt))


@instance_manage_cmd.command("delete")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.pass_context
def delete_cmd(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Delete a Hologres instance."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.delete"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    iid = _resolve_instance_id(instance_id, profile, fmt, op)
    if iid is None:
        return

    try:
        _, hologram_models, _ = _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    region = profile.get("region_id") or "cn-hangzhou"
    try:
        request = hologram_models.DeleteInstanceRequest(region_id=region)
        response = client.delete_instance(iid, request)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={"instance_id": iid, "region_id": region},
    )
    print_output(success(body, fmt))


@instance_manage_cmd.command("stop")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.pass_context
def stop_cmd(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Stop a running Hologres instance."""
    _simple_lifecycle(ctx, "instance-manage.stop", instance_id, "stop_instance")


@instance_manage_cmd.command("resume")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.pass_context
def resume_cmd(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Resume a stopped Hologres instance."""
    _simple_lifecycle(ctx, "instance-manage.resume", instance_id, "resume_instance")


@instance_manage_cmd.command("restart")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.pass_context
def restart_cmd(ctx: click.Context, instance_id: Optional[str]) -> None:
    """Restart a Hologres instance."""
    _simple_lifecycle(ctx, "instance-manage.restart", instance_id, "restart_instance")


# ---------------------------------------------------------------------------
# hologram rename
# ---------------------------------------------------------------------------


@instance_manage_cmd.command("rename")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.option("--instance-name", required=True, help="New display name")
@click.pass_context
def rename_cmd(ctx: click.Context, instance_id: Optional[str],
               instance_name: str) -> None:
    """Rename a Hologres instance."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.rename"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    iid = _resolve_instance_id(instance_id, profile, fmt, op)
    if iid is None:
        return

    try:
        _, hologram_models, _ = _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    try:
        request = hologram_models.UpdateInstanceNameRequest(instance_name=instance_name)
        response = client.update_instance_name(iid, request)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={"instance_id": iid, "new_name": instance_name},
    )
    print_output(success(body, fmt))


# ---------------------------------------------------------------------------
# hologram scale
# ---------------------------------------------------------------------------


_SCALE_TYPES = ["UPGRADE", "DOWNGRADE"]


@instance_manage_cmd.command("scale")
@click.option("--instance-id", default=None,
              help="Hologres instance ID (defaults to profile instance_id)")
@click.option("--scale-type", required=True,
              type=click.Choice(_SCALE_TYPES, case_sensitive=False),
              help="Scaling direction")
@click.option("--cpu", default=None, type=int, help="Target CPU cores")
@click.option("--storage-size", default=None, type=int, help="Target storage size (GB)")
@click.option("--cold-storage-size", default=None, type=int,
              help="Target cold-storage size (GB)")
@click.option("--gateway-count", default=None, type=int,
              help="Target gateway count")
@click.pass_context
def scale_cmd(
    ctx: click.Context,
    instance_id: Optional[str],
    scale_type: str,
    cpu: Optional[int],
    storage_size: Optional[int],
    cold_storage_size: Optional[int],
    gateway_count: Optional[int],
) -> None:
    """Scale a Hologres instance up or down."""
    fmt = ctx.obj.get("format", FORMAT_JSON)
    op = "instance-manage.scale"
    op_start = time.time()

    profile = _resolve_profile(ctx, fmt)
    if profile is None:
        return

    iid = _resolve_instance_id(instance_id, profile, fmt, op)
    if iid is None:
        return

    if cpu is None and storage_size is None and cold_storage_size is None and gateway_count is None:
        log_operation(
            op,
            success=False,
            error_code="NO_CHANGES",
            error_message="No scale target specified",
        )
        print_output(error(
            "NO_CHANGES",
            "Specify at least one of --cpu, --storage-size, --cold-storage-size, "
            "or --gateway-count.",
            fmt,
        ))
        return

    try:
        _, hologram_models, _ = _import_hologram_sdk()
    except ImportError:
        _dependency_missing_error(fmt)
        return

    try:
        client = _create_hologram_client(profile)
    except Exception as exc:
        _credential_error(fmt, exc)
        return

    request_kwargs: dict[str, Any] = {"scale_type": scale_type.upper()}
    if cpu is not None:
        request_kwargs["cpu"] = cpu
    if storage_size is not None:
        request_kwargs["storage_size"] = storage_size
    if cold_storage_size is not None:
        request_kwargs["cold_storage_size"] = cold_storage_size
    if gateway_count is not None:
        request_kwargs["gateway_count"] = gateway_count

    try:
        request = hologram_models.ScaleInstanceRequest(**request_kwargs)
        response = client.scale_instance(iid, request)
    except Exception as exc:
        _handle_api_exception(op, exc, fmt, op_start)
        return

    body = _extract_body(response)
    duration_ms = (time.time() - op_start) * 1000
    log_operation(
        op,
        success=True,
        duration_ms=duration_ms,
        extra={
            "instance_id": iid,
            "scale_type": scale_type.upper(),
            "cpu": cpu,
            "storage_size": storage_size,
            "cold_storage_size": cold_storage_size,
            "gateway_count": gateway_count,
        },
    )
    print_output(success(body, fmt))
