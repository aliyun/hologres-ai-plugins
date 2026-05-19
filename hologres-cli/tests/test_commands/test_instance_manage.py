"""Tests for the ``hologres hologram`` command module."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


# ---------------------------------------------------------------------------
# Shared fixtures / fakes
# ---------------------------------------------------------------------------

MOCK_PROFILE = {
    "name": "test",
    "region_id": "cn-hangzhou",
    "instance_id": "hgpostcn-cn-test123",
    "access_key_id": "test_ak_id",
    "access_key_secret": "test_ak_secret",
    "database": "testdb",
}


class _FakeOpenApiConfig:
    """Stand-in for ``alibabacloud_tea_openapi.models.Config``."""

    def __init__(self, **kwargs):
        self.access_key_id = kwargs.get("access_key_id")
        self.access_key_secret = kwargs.get("access_key_secret")
        self.endpoint = None
        self.read_timeout = None


def _make_fake_request_class(name: str):
    """Build a generic fake request model that records its kwargs."""

    class _FakeRequest:
        __name__ = name

        def __init__(self, **kwargs):
            self._kwargs = kwargs
            for k, v in kwargs.items():
                setattr(self, k, v)

    _FakeRequest.__name__ = name
    return _FakeRequest


_FakeListInstancesRequest = _make_fake_request_class("ListInstancesRequest")
_FakeCreateInstanceRequest = _make_fake_request_class("CreateInstanceRequest")
_FakeDeleteInstanceRequest = _make_fake_request_class("DeleteInstanceRequest")
_FakeUpdateInstanceNameRequest = _make_fake_request_class("UpdateInstanceNameRequest")
_FakeScaleInstanceRequest = _make_fake_request_class("ScaleInstanceRequest")


def _inject_fake_sdk(mocker, *, hologram_client_factory=None, profile=None):
    """Inject fake Alibaba Cloud Hologram SDK modules into ``sys.modules``.

    Also patches ``get_current_profile`` and ``get_profile`` to return the
    supplied *profile* (defaults to ``MOCK_PROFILE``).
    """
    if profile is None:
        profile = MOCK_PROFILE

    mocker.patch(
        "hologres_cli.commands.hologram.get_current_profile",
        return_value=profile,
    )
    mocker.patch(
        "hologres_cli.commands.hologram.get_profile",
        return_value=profile,
    )

    holo_client_mod = MagicMock(name="alibabacloud_hologram20220601.client")
    holo_client_mod.Client = (
        hologram_client_factory if hologram_client_factory is not None else MagicMock()
    )

    holo_models_mod = MagicMock(name="alibabacloud_hologram20220601.models")
    holo_models_mod.ListInstancesRequest = _FakeListInstancesRequest
    holo_models_mod.CreateInstanceRequest = _FakeCreateInstanceRequest
    holo_models_mod.DeleteInstanceRequest = _FakeDeleteInstanceRequest
    holo_models_mod.UpdateInstanceNameRequest = _FakeUpdateInstanceNameRequest
    holo_models_mod.ScaleInstanceRequest = _FakeScaleInstanceRequest

    tea_openapi_mod = MagicMock(name="alibabacloud_tea_openapi.models")
    tea_openapi_mod.Config = _FakeOpenApiConfig

    holo_pkg = MagicMock(name="alibabacloud_hologram20220601")
    holo_pkg.client = holo_client_mod
    holo_pkg.models = holo_models_mod

    tea_openapi_pkg = MagicMock(name="alibabacloud_tea_openapi")
    tea_openapi_pkg.models = tea_openapi_mod

    mocker.patch.dict(
        sys.modules,
        {
            "alibabacloud_hologram20220601": holo_pkg,
            "alibabacloud_hologram20220601.client": holo_client_mod,
            "alibabacloud_hologram20220601.models": holo_models_mod,
            "alibabacloud_tea_openapi": tea_openapi_pkg,
            "alibabacloud_tea_openapi.models": tea_openapi_mod,
        },
    )

    return {
        "holo_client_mod": holo_client_mod,
        "holo_models_mod": holo_models_mod,
        "tea_openapi_mod": tea_openapi_mod,
    }


def _wrap_body(body):
    """Wrap a dict/object as a fake SDK response with a ``.body`` attribute."""
    return SimpleNamespace(body=body)


def _disable_hologram_sdk(mocker):
    """Force imports of Hologram SDK packages to fail."""
    mocker.patch.dict(
        sys.modules,
        {
            "alibabacloud_hologram20220601": None,
            "alibabacloud_hologram20220601.client": None,
            "alibabacloud_hologram20220601.models": None,
            "alibabacloud_tea_openapi": None,
            "alibabacloud_tea_openapi.models": None,
        },
    )


# ---------------------------------------------------------------------------
# _create_hologram_client
# ---------------------------------------------------------------------------


class TestCreateHologramClient:
    """Tests for the ``_create_hologram_client`` helper."""

    def test_creates_client_with_correct_endpoint_and_credentials(self, mocker):
        captured_config = {}

        def _fake_client_factory(config):
            captured_config["config"] = config
            return MagicMock(name="HologramClient")

        _inject_fake_sdk(
            mocker,
            hologram_client_factory=_fake_client_factory,
            profile={
                "region_id": "cn-shanghai",
                "access_key_id": "ak-x",
                "access_key_secret": "sk-y",
            },
        )

        from hologres_cli.commands.instance_manage import _create_hologram_client

        client = _create_hologram_client(
            {
                "region_id": "cn-shanghai",
                "access_key_id": "ak-x",
                "access_key_secret": "sk-y",
            }
        )

        assert client is not None
        cfg = captured_config["config"]
        assert cfg.access_key_id == "ak-x"
        assert cfg.access_key_secret == "sk-y"
        assert cfg.endpoint == "hologram.cn-shanghai.aliyuncs.com"
        assert cfg.read_timeout == 20000

    def test_defaults_region_when_missing(self, mocker):
        captured = {}

        def _factory(config):
            captured["config"] = config
            return MagicMock()

        _inject_fake_sdk(mocker, hologram_client_factory=_factory)

        from hologres_cli.commands.instance_manage import _create_hologram_client

        _create_hologram_client(
            {"access_key_id": "ak", "access_key_secret": "sk"}
        )

        assert captured["config"].endpoint == "hologram.cn-hangzhou.aliyuncs.com"

    def test_raises_when_ak_missing(self, mocker):
        _inject_fake_sdk(mocker, hologram_client_factory=MagicMock())

        from hologres_cli.commands.instance_manage import _create_hologram_client

        with pytest.raises(ValueError, match="access_key_id"):
            _create_hologram_client({"access_key_secret": "sk"})

    def test_raises_when_sk_missing(self, mocker):
        _inject_fake_sdk(mocker, hologram_client_factory=MagicMock())

        from hologres_cli.commands.instance_manage import _create_hologram_client

        with pytest.raises(ValueError, match="access_key_secret"):
            _create_hologram_client({"access_key_id": "ak"})


# ---------------------------------------------------------------------------
# hologram list
# ---------------------------------------------------------------------------


class TestHologramListCmd:
    def test_list_success(self, mocker):
        instances = [
            {"instanceId": "hgpostcn-cn-1", "instanceName": "i1", "status": "Running"},
            {"instanceId": "hgpostcn-cn-2", "instanceName": "i2", "status": "Stopped"},
        ]
        fake_client = MagicMock()
        fake_client.list_instances.return_value = _wrap_body(
            {"instanceList": instances, "requestId": "req-1"}
        )

        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "list"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        assert len(rows) == 2
        assert {r["instanceId"] for r in rows} == {"hgpostcn-cn-1", "hgpostcn-cn-2"}

        # SDK call inspection
        fake_client.list_instances.assert_called_once()
        request = fake_client.list_instances.call_args[0][0]
        assert request.resource_group_id is None

    def test_list_with_resource_group(self, mocker):
        fake_client = MagicMock()
        fake_client.list_instances.return_value = _wrap_body(
            {"instanceList": [], "requestId": "rq"}
        )

        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "list", "--resource-group-id", "rg-foo"]
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        request = fake_client.list_instances.call_args[0][0]
        assert request.resource_group_id == "rg-foo"

    def test_list_empty_falls_back_to_body(self, mocker):
        """When no instances, raw body (with requestId) is returned."""
        fake_client = MagicMock()
        fake_client.list_instances.return_value = _wrap_body(
            {"instanceList": [], "requestId": "rq-empty", "totalCount": 0}
        )
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "list"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        # success() wraps the body dict directly under "data"
        assert output["data"]["requestId"] == "rq-empty"

    def test_list_dependency_missing(self, mocker):
        mocker.patch(
            "hologres_cli.commands.hologram.get_current_profile",
            return_value=MOCK_PROFILE,
        )
        _disable_hologram_sdk(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DEPENDENCY_MISSING"
        assert "pip install" in output["error"]["message"]

    def test_list_credentials_missing(self, mocker):
        fake_client = MagicMock()
        _inject_fake_sdk(
            mocker,
            hologram_client_factory=MagicMock(return_value=fake_client),
            profile={"region_id": "cn-hangzhou"},  # no AK/SK
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CREDENTIAL_ERROR"
        assert "access_key_id" in output["error"]["message"]

    def test_list_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.list_instances.side_effect = RuntimeError("boom")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "boom" in output["error"]["message"]


# ---------------------------------------------------------------------------
# hologram get
# ---------------------------------------------------------------------------


class TestHologramGetCmd:
    def test_get_success_with_instance_id(self, mocker):
        fake_client = MagicMock()
        fake_client.get_instance.return_value = _wrap_body(
            {"instanceId": "hgpostcn-cn-abc", "status": "Running"}
        )
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "get", "--instance-id", "hgpostcn-cn-abc"]
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["instanceId"] == "hgpostcn-cn-abc"
        fake_client.get_instance.assert_called_once_with("hgpostcn-cn-abc")

    def test_get_falls_back_to_profile_instance_id(self, mocker):
        """No --instance-id passed: falls back to profile['instance_id']."""
        fake_client = MagicMock()
        fake_client.get_instance.return_value = _wrap_body({"instanceId": "x"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "get"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        # Should have used MOCK_PROFILE["instance_id"]
        fake_client.get_instance.assert_called_once_with(MOCK_PROFILE["instance_id"])

    def test_get_cli_overrides_profile_instance_id(self, mocker):
        fake_client = MagicMock()
        fake_client.get_instance.return_value = _wrap_body({"instanceId": "x"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "get", "--instance-id", "override-id"]
        )

        assert result.exit_code == 0, result.output
        fake_client.get_instance.assert_called_once_with("override-id")

    def test_get_missing_instance_id_errors(self, mocker):
        """No CLI --instance-id and no profile.instance_id => INVALID_INPUT."""
        fake_client = MagicMock()
        _inject_fake_sdk(
            mocker,
            hologram_client_factory=MagicMock(return_value=fake_client),
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "ak",
                "access_key_secret": "sk",
                # no instance_id!
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "get"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"
        assert "instance-id" in output["error"]["message"]
        fake_client.get_instance.assert_not_called()

    def test_get_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.get_instance.side_effect = RuntimeError("network down")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "get"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "network down" in output["error"]["message"]


# ---------------------------------------------------------------------------
# hologram create
# ---------------------------------------------------------------------------


class TestHologramCreateCmd:
    def _required_args(self, **overrides):
        args = [
            "instance-manage", "create",
            "--instance-name", "my-holo",
            "--instance-type", "Standard",
            "--charge-type", "PostPaid",
            "--zone-id", "cn-hangzhou-h",
            "--vpc-id", "vpc-xxx",
            "--vswitch-id", "vsw-xxx",
        ]
        for k, v in overrides.items():
            args.extend([k, v])
        return args

    def test_create_success(self, mocker):
        fake_client = MagicMock()
        fake_client.create_instance.return_value = _wrap_body(
            {"orderId": "ord-1", "instanceId": "hgpostcn-cn-new"}
        )
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, self._required_args(**{"--cpu": "32", "--storage-size": "100"})
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["instanceId"] == "hgpostcn-cn-new"

        fake_client.create_instance.assert_called_once()
        request = fake_client.create_instance.call_args[0][0]
        assert request.instance_name == "my-holo"
        assert request.instance_type == "Standard"
        assert request.charge_type == "PostPaid"
        assert request.zone_id == "cn-hangzhou-h"
        assert request.vpc_id == "vpc-xxx"
        assert request.v_switch_id == "vsw-xxx"
        assert request.cpu == 32
        assert request.storage_size == 100
        assert request.region_id == MOCK_PROFILE["region_id"]
        assert request.auto_pay is True

    def test_create_region_override(self, mocker):
        fake_client = MagicMock()
        fake_client.create_instance.return_value = _wrap_body({"orderId": "ord"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, self._required_args(**{"--region-id": "cn-shanghai"})
        )

        assert result.exit_code == 0, result.output
        request = fake_client.create_instance.call_args[0][0]
        assert request.region_id == "cn-shanghai"

    def test_create_with_optional_fields(self, mocker):
        fake_client = MagicMock()
        fake_client.create_instance.return_value = _wrap_body({"orderId": "ord"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            self._required_args(
                **{
                    "--gateway-count": "2",
                    "--leader-instance-id": "leader-xx",
                }
            )
            + ["--no-auto-pay"],
        )

        assert result.exit_code == 0, result.output
        request = fake_client.create_instance.call_args[0][0]
        assert request.gateway_count == 2
        assert request.leader_instance_id == "leader-xx"
        assert request.auto_pay is False

    def test_create_dependency_missing(self, mocker):
        mocker.patch(
            "hologres_cli.commands.hologram.get_current_profile",
            return_value=MOCK_PROFILE,
        )
        _disable_hologram_sdk(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, self._required_args())

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DEPENDENCY_MISSING"

    def test_create_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.create_instance.side_effect = RuntimeError("quota exceeded")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, self._required_args())

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "quota exceeded" in output["error"]["message"]


# ---------------------------------------------------------------------------
# hologram delete
# ---------------------------------------------------------------------------


class TestHologramDeleteCmd:
    def test_delete_success(self, mocker):
        fake_client = MagicMock()
        fake_client.delete_instance.return_value = _wrap_body({"requestId": "r"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "delete", "--instance-id", "hgpostcn-cn-x"]
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        fake_client.delete_instance.assert_called_once()
        # Positional args: instance_id, request
        args, _kwargs = fake_client.delete_instance.call_args
        assert args[0] == "hgpostcn-cn-x"
        assert args[1].region_id == MOCK_PROFILE["region_id"]

    def test_delete_falls_back_to_profile_instance(self, mocker):
        fake_client = MagicMock()
        fake_client.delete_instance.return_value = _wrap_body({"requestId": "r"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "delete"])

        assert result.exit_code == 0, result.output
        args, _ = fake_client.delete_instance.call_args
        assert args[0] == MOCK_PROFILE["instance_id"]

    def test_delete_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.delete_instance.side_effect = RuntimeError("forbidden")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "delete"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "forbidden" in output["error"]["message"]


# ---------------------------------------------------------------------------
# hologram stop / resume / restart (lifecycle helpers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcmd,sdk_method",
    [
        ("stop", "stop_instance"),
        ("resume", "resume_instance"),
        ("restart", "restart_instance"),
    ],
)
class TestHologramLifecycleCmds:
    def test_lifecycle_success(self, mocker, subcmd, sdk_method):
        fake_client = MagicMock()
        getattr(fake_client, sdk_method).return_value = _wrap_body(
            {"requestId": "req-id"}
        )
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", subcmd, "--instance-id", "hgpostcn-cn-x"]
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        getattr(fake_client, sdk_method).assert_called_once_with("hgpostcn-cn-x")

    def test_lifecycle_uses_profile_instance(self, mocker, subcmd, sdk_method):
        fake_client = MagicMock()
        getattr(fake_client, sdk_method).return_value = _wrap_body({"requestId": "r"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", subcmd])

        assert result.exit_code == 0, result.output
        getattr(fake_client, sdk_method).assert_called_once_with(
            MOCK_PROFILE["instance_id"]
        )

    def test_lifecycle_invalid_when_no_instance_id(
        self, mocker, subcmd, sdk_method
    ):
        fake_client = MagicMock()
        _inject_fake_sdk(
            mocker,
            hologram_client_factory=MagicMock(return_value=fake_client),
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "ak",
                "access_key_secret": "sk",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", subcmd])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"
        getattr(fake_client, sdk_method).assert_not_called()

    def test_lifecycle_api_error(self, mocker, subcmd, sdk_method):
        fake_client = MagicMock()
        getattr(fake_client, sdk_method).side_effect = RuntimeError("oops")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", subcmd])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "oops" in output["error"]["message"]


# ---------------------------------------------------------------------------
# hologram rename
# ---------------------------------------------------------------------------


class TestHologramRenameCmd:
    def test_rename_success(self, mocker):
        fake_client = MagicMock()
        fake_client.update_instance_name.return_value = _wrap_body({"requestId": "r"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "instance-manage", "rename",
                "--instance-id", "hgpostcn-cn-x",
                "--instance-name", "fresh-name",
            ],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True

        fake_client.update_instance_name.assert_called_once()
        args, _ = fake_client.update_instance_name.call_args
        assert args[0] == "hgpostcn-cn-x"
        assert args[1].instance_name == "fresh-name"

    def test_rename_uses_profile_instance(self, mocker):
        fake_client = MagicMock()
        fake_client.update_instance_name.return_value = _wrap_body({"requestId": "r"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "rename", "--instance-name", "renamed"]
        )

        assert result.exit_code == 0, result.output
        args, _ = fake_client.update_instance_name.call_args
        assert args[0] == MOCK_PROFILE["instance_id"]
        assert args[1].instance_name == "renamed"

    def test_rename_requires_instance_name(self, mocker):
        _inject_fake_sdk(mocker, hologram_client_factory=MagicMock())

        runner = CliRunner()
        result = runner.invoke(cli, ["instance-manage", "rename"])

        # Click usage error
        assert result.exit_code != 0
        combined = (result.output or "") + (
            result.stderr if result.stderr_bytes is not None else ""
        )
        assert "--instance-name" in combined

    def test_rename_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.update_instance_name.side_effect = RuntimeError("denied")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["instance-manage", "rename", "--instance-name", "n"]
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"


# ---------------------------------------------------------------------------
# hologram scale
# ---------------------------------------------------------------------------


class TestHologramScaleCmd:
    def test_scale_success_cpu(self, mocker):
        fake_client = MagicMock()
        fake_client.scale_instance.return_value = _wrap_body(
            {"orderId": "scale-ord"}
        )
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "instance-manage", "scale",
                "--instance-id", "hgpostcn-cn-x",
                "--scale-type", "UPGRADE",
                "--cpu", "64",
            ],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True

        args, _ = fake_client.scale_instance.call_args
        assert args[0] == "hgpostcn-cn-x"
        assert args[1].scale_type == "UPGRADE"
        assert args[1].cpu == 64

    def test_scale_with_multiple_fields(self, mocker):
        fake_client = MagicMock()
        fake_client.scale_instance.return_value = _wrap_body({"orderId": "o"})
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "instance-manage", "scale",
                "--scale-type", "DOWNGRADE",
                "--cpu", "16",
                "--storage-size", "200",
                "--cold-storage-size", "1000",
                "--gateway-count", "3",
            ],
        )

        assert result.exit_code == 0, result.output
        args, _ = fake_client.scale_instance.call_args
        req = args[1]
        assert req.scale_type == "DOWNGRADE"
        assert req.cpu == 16
        assert req.storage_size == 200
        assert req.cold_storage_size == 1000
        assert req.gateway_count == 3

    def test_scale_no_changes_error(self, mocker):
        """No cpu/storage/etc. given => NO_CHANGES error before SDK call."""
        fake_client = MagicMock()
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "instance-manage", "scale",
                "--instance-id", "hgpostcn-cn-x",
                "--scale-type", "UPGRADE",
            ],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NO_CHANGES"
        # SDK must not have been called
        fake_client.scale_instance.assert_not_called()

    def test_scale_missing_instance_id(self, mocker):
        fake_client = MagicMock()
        _inject_fake_sdk(
            mocker,
            hologram_client_factory=MagicMock(return_value=fake_client),
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "ak",
                "access_key_secret": "sk",
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["instance-manage", "scale", "--scale-type", "UPGRADE", "--cpu", "32"],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"
        fake_client.scale_instance.assert_not_called()

    def test_scale_api_error(self, mocker):
        fake_client = MagicMock()
        fake_client.scale_instance.side_effect = RuntimeError("oversold")
        _inject_fake_sdk(
            mocker, hologram_client_factory=MagicMock(return_value=fake_client)
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "instance-manage", "scale",
                "--scale-type", "UPGRADE",
                "--cpu", "32",
            ],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        assert "oversold" in output["error"]["message"]
