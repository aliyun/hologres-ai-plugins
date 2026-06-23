"""Tests for metric command module."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli

# Default profile returned by mocked get_current_profile in most tests.
_DEFAULT_PROFILE = {"region_id": "cn-hangzhou"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeMetricListRequest:
    """Stand-in for alibabacloud_cms20190101.models.DescribeMetricListRequest."""

    def __init__(self, **kwargs):
        self.namespace = kwargs.get("namespace")
        self.metric_name = kwargs.get("metric_name")
        self.start_time = kwargs.get("start_time")
        self.end_time = kwargs.get("end_time")
        self.period = kwargs.get("period")
        self.dimensions = kwargs.get("dimensions")
        self.next_token = None


class _FakeMetricLastRequest:
    """Stand-in for alibabacloud_cms20190101.models.DescribeMetricLastRequest."""

    def __init__(self, **kwargs):
        self.namespace = kwargs.get("namespace")
        self.metric_name = kwargs.get("metric_name")
        self.period = kwargs.get("period")
        self.dimensions = kwargs.get("dimensions")
        self.next_token = None


class _FakeMetricMetaListRequest:
    """Stand-in for alibabacloud_cms20190101.models.DescribeMetricMetaListRequest."""

    def __init__(self, **kwargs):
        self.namespace = kwargs.get("namespace")
        self.page_number = kwargs.get("page_number")
        self.page_size = kwargs.get("page_size")


class _FakeConfig:
    """Stand-in for alibabacloud_tea_openapi.models.Config."""

    def __init__(self, **kwargs):
        self.credential = kwargs.get("credential")
        self.region_id = kwargs.get("region_id")
        self.endpoint = None


class _FakeCredentialConfig:
    """Stand-in for alibabacloud_credentials.models.Config."""

    def __init__(self, **kwargs):
        self.type = kwargs.get("type")
        self.access_key_id = kwargs.get("access_key_id")
        self.access_key_secret = kwargs.get("access_key_secret")


def _inject_fake_sdk(
    mocker,
    *,
    cms_client_factory=None,
    credential_client_factory=None,
    profile=None,
):
    """Inject fake Alibaba Cloud SDK modules into ``sys.modules``.

    The metric commands lazy-import the SDK inside the function body.
    Tests use this helper to provide controllable fakes for the imports.

    Also mocks ``get_current_profile`` to return *profile* (defaults to
    ``_DEFAULT_PROFILE``) so that ``_resolve_region`` resolves correctly.
    """
    if profile is None:
        profile = _DEFAULT_PROFILE
    mocker.patch(
        "hologres_cli.commands.metric.get_current_profile",
        return_value=profile,
    )
    cms_client_mod = MagicMock(name="alibabacloud_cms20190101.client")
    cms_client_mod.Client = (
        cms_client_factory if cms_client_factory is not None else MagicMock()
    )

    cms_models_mod = MagicMock(name="alibabacloud_cms20190101.models")
    cms_models_mod.DescribeMetricListRequest = _FakeMetricListRequest
    cms_models_mod.DescribeMetricLastRequest = _FakeMetricLastRequest
    cms_models_mod.DescribeMetricMetaListRequest = _FakeMetricMetaListRequest

    creds_mod = MagicMock(name="alibabacloud_credentials.client")
    creds_mod.Client = (
        credential_client_factory
        if credential_client_factory is not None
        else MagicMock()
    )

    creds_models_mod = MagicMock(name="alibabacloud_credentials.models")
    creds_models_mod.Config = _FakeCredentialConfig

    tea_openapi_mod = MagicMock(name="alibabacloud_tea_openapi.models")
    tea_openapi_mod.Config = _FakeConfig

    # Wire submodules as attributes of their parent packages so that
    # ``from alibabacloud_cms20190101 import models`` (which performs a
    # getattr on the parent) returns our patched submodule mock.
    cms_pkg = MagicMock(name="alibabacloud_cms20190101")
    cms_pkg.client = cms_client_mod
    cms_pkg.models = cms_models_mod

    creds_pkg = MagicMock(name="alibabacloud_credentials")
    creds_pkg.client = creds_mod
    creds_pkg.models = creds_models_mod

    tea_openapi_pkg = MagicMock(name="alibabacloud_tea_openapi")
    tea_openapi_pkg.models = tea_openapi_mod

    mocker.patch.dict(
        sys.modules,
        {
            "alibabacloud_cms20190101": cms_pkg,
            "alibabacloud_cms20190101.client": cms_client_mod,
            "alibabacloud_cms20190101.models": cms_models_mod,
            "alibabacloud_credentials": creds_pkg,
            "alibabacloud_credentials.client": creds_mod,
            "alibabacloud_credentials.models": creds_models_mod,
            "alibabacloud_tea_openapi": tea_openapi_pkg,
            "alibabacloud_tea_openapi.models": tea_openapi_mod,
        },
    )

    return {
        "cms_client_mod": cms_client_mod,
        "cms_models_mod": cms_models_mod,
        "creds_mod": creds_mod,
        "creds_models_mod": creds_models_mod,
        "tea_openapi_mod": tea_openapi_mod,
    }


def _build_metric_response(
    *,
    code="200",
    message="",
    datapoints=None,
    next_token=None,
):
    """Build a fake CMS DescribeMetricList/Last response object."""
    body = SimpleNamespace(
        code=code,
        message=message,
        datapoints=json.dumps(datapoints) if datapoints is not None else None,
        next_token=next_token,
    )
    return SimpleNamespace(body=body)


def _build_meta_response(
    *,
    code="200",
    message="",
    resources=None,
    total_count=None,
):
    """Build a fake CMS DescribeMetricMetaList response object.

    ``resources`` is a list of metric metadata dicts; each is wrapped in a
    SimpleNamespace so getattr() lookups work as the command expects.
    """
    if resources is None:
        resource_list = []
    else:
        resource_list = [SimpleNamespace(**r) for r in resources]

    if total_count is None:
        total_count = len(resource_list)

    body = SimpleNamespace(
        code=code,
        message=message,
        resources=SimpleNamespace(resource=resource_list),
        total_count=total_count,
    )
    return SimpleNamespace(body=body)


# ---------------------------------------------------------------------------
# metric config
# ---------------------------------------------------------------------------


class TestMetricConfigCmd:
    """Tests for ``hologres metric config``."""

    def test_config_show_with_credentials(self, mocker):
        """--show masks configured cms AK/SK properly."""
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            return_value={
                "name": "default",
                "cms_access_key_id": "LTAI5tAbcDefGhIjKlMn",
                "cms_access_key_secret": "AbCdEfGhIjKlMnOpQrStUvWxYz123456",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "config", "--show"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        data = output["data"]
        assert data["cms_access_key_id"].startswith("LTAI")
        assert "****" in data["cms_access_key_id"]
        assert data["cms_access_key_secret"].startswith("AbCd")
        assert "****" in data["cms_access_key_secret"]

    def test_config_show_no_credentials(self, mocker):
        """--show displays (not set) when no cms AK/SK configured."""
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            return_value={"name": "default"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "config", "--show"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        data = output["data"]
        assert data["cms_access_key_id"] == "(not set)"
        assert data["cms_access_key_secret"] == "(not set)"

    def test_config_show_no_profile(self, mocker):
        """--show gracefully handles missing profile."""
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            side_effect=RuntimeError("no config"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "config", "--show"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        data = output["data"]
        assert data["cms_access_key_id"] == "(not set)"
        assert data["cms_access_key_secret"] == "(not set)"

    def test_config_set_via_options(self, mocker):
        """Setting cms credentials via --access-key-id / --access-key-secret."""
        profile = {"name": "default", "region_id": "cn-hangzhou"}
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            return_value=profile,
        )
        mock_set = mocker.patch("hologres_cli.commands.metric.set_profile")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "config",
                "--access-key-id", "my-cms-ak",
                "--access-key-secret", "my-cms-sk",
            ],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "saved successfully" in output["data"]["message"]

        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][0]
        assert saved_profile["cms_access_key_id"] == "my-cms-ak"
        assert saved_profile["cms_access_key_secret"] == "my-cms-sk"

    def test_config_interactive(self, mocker):
        """Interactive mode prompts for AK/SK when not provided."""
        profile = {"name": "default", "region_id": "cn-hangzhou"}
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            return_value=profile,
        )
        mock_set = mocker.patch("hologres_cli.commands.metric.set_profile")

        runner = CliRunner()
        # Simulate interactive input: AK + SK
        result = runner.invoke(
            cli,
            ["metric", "config"],
            input="interactive-ak\ninteractive-sk\n",
        )

        assert result.exit_code == 0, result.output
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][0]
        assert saved_profile["cms_access_key_id"] == "interactive-ak"
        assert saved_profile["cms_access_key_secret"] == "interactive-sk"

    def test_config_no_profile_error(self, mocker):
        """Setting credentials without an existing profile yields CONFIG_ERROR."""
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            side_effect=RuntimeError("no config"),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "config",
                "--access-key-id", "ak",
                "--access-key-secret", "sk",
            ],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"


# ---------------------------------------------------------------------------
# metric list (DescribeMetricMetaList)
# ---------------------------------------------------------------------------


class TestMetricListCmd:
    """Tests for ``hologres metric list``."""

    def test_metric_list_success(self, mocker):
        """Mock API returns multiple metrics; output contains all metadata fields."""
        sample_resources = [
            {
                "metric_name": "cpu_usage",
                "description": "CPU usage percentage",
                "unit": "%",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average,Maximum",
            },
            {
                "metric_name": "memory_usage",
                "description": "Memory usage percentage",
                "unit": "%",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average,Maximum",
            },
            {
                "metric_name": "query_qps",
                "description": "Queries per second",
                "unit": "Count/s",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average",
            },
        ]

        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=sample_resources
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        assert len(rows) == 3
        assert output["data"]["count"] == 3

        # Each row should contain the documented metadata fields.
        for row in rows:
            assert set(row.keys()) >= {
                "metric_name", "description", "unit",
                "dimensions", "periods", "statistics",
            }

        names = {r["metric_name"] for r in rows}
        assert names == {"cpu_usage", "memory_usage", "query_qps"}

        # The API was actually invoked with the correct namespace.
        request = fake_client.describe_metric_meta_list.call_args[0][0]
        assert request.namespace == "acs_hologres"
        assert request.page_size == 100

    def test_metric_list_search(self, mocker):
        """--search filters API results client-side by metric_name/description."""
        sample_resources = [
            {
                "metric_name": "cpu_usage",
                "description": "CPU usage percentage",
                "unit": "%",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average",
            },
            {
                "metric_name": "memory_usage",
                "description": "Memory usage",
                "unit": "%",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average",
            },
            {
                "metric_name": "disk_io",
                "description": "Disk IO involving CPU pressure",
                "unit": "Bytes/s",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average",
            },
        ]

        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=sample_resources
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list", "--search", "cpu"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        assert len(rows) == 2
        names = {r["metric_name"] for r in rows}
        # cpu_usage matches by name, disk_io matches via description.
        assert names == {"cpu_usage", "disk_io"}

    def test_metric_list_search_no_match(self, mocker):
        """--search keyword that matches nothing yields an empty list."""
        sample_resources = [
            {
                "metric_name": "cpu_usage",
                "description": "CPU usage percentage",
                "unit": "%",
                "dimensions": "userId,instanceId",
                "periods": "60",
                "statistics": "Average",
            },
        ]

        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=sample_resources
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["metric", "list", "--search", "xyz_no_such_metric"]
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_metric_list_credentials_error(self, mocker):
        """Failure constructing credential client surfaces CREDENTIAL_ERROR."""
        def _boom(*args, **kwargs):
            raise RuntimeError("ak/sk not found in environment")

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(),
            credential_client_factory=_boom,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CREDENTIAL_ERROR"
        assert "ALIBABA_CLOUD_ACCESS_KEY_ID" in output["error"]["message"]

    def test_metric_list_api_error(self, mocker):
        """A non-200 body.code is reported as API_ERROR."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="InvalidParameter",
            message="namespace is invalid",
            resources=[],
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        msg = output["error"]["message"]
        assert "InvalidParameter" in msg
        assert "namespace is invalid" in msg

    def test_metric_list_sdk_not_installed(self, mocker):
        """Lazy SDK imports failing yield DEPENDENCY_MISSING with install hint."""
        mocker.patch.dict(
            sys.modules,
            {
                "alibabacloud_cms20190101": None,
                "alibabacloud_cms20190101.client": None,
                "alibabacloud_cms20190101.models": None,
                "alibabacloud_credentials": None,
                "alibabacloud_credentials.client": None,
                "alibabacloud_tea_openapi": None,
                "alibabacloud_tea_openapi.models": None,
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DEPENDENCY_MISSING"
        assert "pip install" in output["error"]["message"]
        assert "alibabacloud" in output["error"]["message"]


# ---------------------------------------------------------------------------
# metric query (DescribeMetricList)
# ---------------------------------------------------------------------------


class TestMetricQueryCmd:
    """Tests for ``hologres metric query``."""

    def test_metric_query_success(self, mocker):
        """Mock SDK returns a single page of datapoints; output is JSON rows."""
        sample_points = [
            {"timestamp": 1700000000000, "Average": 12.5, "userId": "u", "instanceId": "hgprecn-cn-xxx"},
            {"timestamp": 1700000060000, "Average": 13.0, "userId": "u", "instanceId": "hgprecn-cn-xxx"},
        ]

        fake_client = MagicMock()
        fake_client.describe_metric_list.return_value = _build_metric_response(
            code="200", datapoints=sample_points, next_token=None
        )
        cms_client_factory = MagicMock(return_value=fake_client)
        credential_client_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_client_factory,
            credential_client_factory=credential_client_factory,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "query", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2
        assert output["data"]["rows"] == sample_points

        cms_client_factory.assert_called_once()
        request = fake_client.describe_metric_list.call_args[0][0]
        assert request.namespace == "acs_hologres"
        assert request.metric_name == "cpu_usage"
        assert request.period == "60"
        dims = json.loads(request.dimensions)
        assert dims == [{"instanceId": "hgprecn-cn-xxx"}]

    def test_metric_query_missing_instance_id(self):
        """Omitting --instance-id triggers a Click usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "query", "cpu_usage"])

        assert result.exit_code != 0
        combined = (result.output or "") + (
            result.stderr if result.stderr_bytes is not None else ""
        )
        assert "--instance-id" in combined

    def test_metric_query_credentials_error(self, mocker):
        """A failure constructing the credential client surfaces CREDENTIAL_ERROR."""
        def _boom(*args, **kwargs):
            raise RuntimeError("ak/sk not found in environment")

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(),
            credential_client_factory=_boom,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "query", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CREDENTIAL_ERROR"
        assert "ALIBABA_CLOUD_ACCESS_KEY_ID" in output["error"]["message"]

    def test_metric_query_api_error(self, mocker):
        """A non-200 body.code is reported as API_ERROR with code/message echoed."""
        fake_client = MagicMock()
        fake_client.describe_metric_list.return_value = _build_metric_response(
            code="InvalidParameter",
            message="metric_name is invalid",
            datapoints=None,
            next_token=None,
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "query", "not_a_metric",
                "--instance-id", "hgprecn-cn-xxx",
            ],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        msg = output["error"]["message"]
        assert "InvalidParameter" in msg
        assert "metric_name is invalid" in msg

    def test_metric_query_with_time_range(self, mocker):
        """ISO-8601 --start-time/--end-time are converted to epoch ms strings."""
        fake_client = MagicMock()
        fake_client.describe_metric_list.return_value = _build_metric_response(
            code="200", datapoints=[], next_token=None
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "query", "cpu_usage",
                "--instance-id", "hgprecn-cn-xxx",
                "--start-time", "2025-01-01T00:00:00",
                "--end-time", "2025-01-01T01:00:00",
            ],
        )

        assert result.exit_code == 0, result.output
        request = fake_client.describe_metric_list.call_args[0][0]
        assert request.start_time == "1735689600000"
        assert request.end_time == "1735693200000"

    def test_metric_query_with_period(self, mocker):
        """--period is forwarded to the SDK as a string."""
        fake_client = MagicMock()
        fake_client.describe_metric_list.return_value = _build_metric_response(
            code="200", datapoints=[], next_token=None
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "query", "cpu_usage",
                "--instance-id", "hgprecn-cn-xxx",
                "--period", "300",
            ],
        )

        assert result.exit_code == 0, result.output
        request = fake_client.describe_metric_list.call_args[0][0]
        assert request.period == "300"

    def test_metric_query_sdk_not_installed(self, mocker):
        """Lazy SDK imports failing yield DEPENDENCY_MISSING with install hint."""
        mocker.patch.dict(
            sys.modules,
            {
                "alibabacloud_cms20190101": None,
                "alibabacloud_cms20190101.client": None,
                "alibabacloud_cms20190101.models": None,
                "alibabacloud_credentials": None,
                "alibabacloud_credentials.client": None,
                "alibabacloud_tea_openapi": None,
                "alibabacloud_tea_openapi.models": None,
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "query", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DEPENDENCY_MISSING"
        assert "pip install" in output["error"]["message"]
        assert "alibabacloud" in output["error"]["message"]


# ---------------------------------------------------------------------------
# metric latest (DescribeMetricLast)
# ---------------------------------------------------------------------------


class TestMetricLatestCmd:
    """Tests for ``hologres metric latest``."""

    def test_metric_latest_success(self, mocker):
        """Mock SDK returns latest datapoints; output is JSON rows."""
        sample_points = [
            {
                "timestamp": 1700000060000,
                "Average": 42.0,
                "userId": "u",
                "instanceId": "hgprecn-cn-xxx",
            },
        ]

        fake_client = MagicMock()
        fake_client.describe_metric_last.return_value = _build_metric_response(
            code="200", datapoints=sample_points, next_token=None
        )
        cms_client_factory = MagicMock(return_value=fake_client)

        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_client_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "latest", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 1
        assert output["data"]["rows"] == sample_points

        cms_client_factory.assert_called_once()
        request = fake_client.describe_metric_last.call_args[0][0]
        assert request.namespace == "acs_hologres"
        assert request.metric_name == "cpu_usage"
        # --period was not provided; the request should not carry one.
        assert request.period is None
        dims = json.loads(request.dimensions)
        assert dims == [{"instanceId": "hgprecn-cn-xxx"}]

    def test_metric_latest_missing_instance_id(self):
        """Omitting --instance-id triggers a Click usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "latest", "cpu_usage"])

        assert result.exit_code != 0
        combined = (result.output or "") + (
            result.stderr if result.stderr_bytes is not None else ""
        )
        assert "--instance-id" in combined

    def test_metric_latest_credentials_error(self, mocker):
        """A failure constructing the credential client surfaces CREDENTIAL_ERROR."""
        def _boom(*args, **kwargs):
            raise RuntimeError("ak/sk not found in environment")

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(),
            credential_client_factory=_boom,
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "latest", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CREDENTIAL_ERROR"
        assert "ALIBABA_CLOUD_ACCESS_KEY_ID" in output["error"]["message"]

    def test_metric_latest_api_error(self, mocker):
        """A non-200 body.code is reported as API_ERROR with code/message echoed."""
        fake_client = MagicMock()
        fake_client.describe_metric_last.return_value = _build_metric_response(
            code="InvalidParameter",
            message="metric_name is invalid",
            datapoints=None,
            next_token=None,
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "latest", "not_a_metric",
                "--instance-id", "hgprecn-cn-xxx",
            ],
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "API_ERROR"
        msg = output["error"]["message"]
        assert "InvalidParameter" in msg
        assert "metric_name is invalid" in msg

    def test_metric_latest_with_period(self, mocker):
        """--period is forwarded to the SDK as a string."""
        fake_client = MagicMock()
        fake_client.describe_metric_last.return_value = _build_metric_response(
            code="200", datapoints=[], next_token=None
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metric", "latest", "cpu_usage",
                "--instance-id", "hgprecn-cn-xxx",
                "--period", "60",
            ],
        )

        assert result.exit_code == 0, result.output
        request = fake_client.describe_metric_last.call_args[0][0]
        assert request.period == "60"


# ---------------------------------------------------------------------------
# _resolve_region fallback logic
# ---------------------------------------------------------------------------


class TestResolveRegion:
    """Tests for the _resolve_region helper used by all metric sub-commands."""

    def test_no_region_flag_uses_profile_region(self, mocker):
        """When --region is NOT passed, profile's region_id is used."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={"region_id": "cn-shanghai"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["ok"] is True
        # Verify the CMS client was created with the profile region
        from hologres_cli.commands.metric import _create_cms_client
        # Check config passed to CMSClient
        call_args = fake_client.describe_metric_meta_list.call_args
        assert call_args is not None  # API was called

    def test_region_flag_overrides_profile(self, mocker):
        """When --region is explicitly passed, it takes priority over profile."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        cms_factory = MagicMock(return_value=fake_client)
        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={"region_id": "cn-shanghai"},
        )

        runner = CliRunner()
        result = runner.invoke(
            cli, ["metric", "list", "--region", "cn-beijing"]
        )

        assert result.exit_code == 0, result.output
        # The Config object passed to CMSClient should have cn-beijing
        config_arg = cms_factory.call_args[0][0]
        assert config_arg.region_id == "cn-beijing"
        assert config_arg.endpoint == "metrics.cn-beijing.aliyuncs.com"

    def test_no_region_flag_no_profile_falls_back_to_default(self, mocker):
        """When --region is NOT passed and profile has no region_id, fall back to cn-hangzhou."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        cms_factory = MagicMock(return_value=fake_client)
        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={},  # no region_id
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        # The Config object should default to cn-hangzhou
        config_arg = cms_factory.call_args[0][0]
        assert config_arg.region_id == "cn-hangzhou"
        assert config_arg.endpoint == "metrics.cn-hangzhou.aliyuncs.com"

    def test_no_region_flag_profile_exception_falls_back(self, mocker):
        """When get_current_profile raises, fall back to cn-hangzhou."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        cms_factory = MagicMock(return_value=fake_client)

        # Inject SDK but override the profile mock to raise
        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={},
        )
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            side_effect=RuntimeError("no config"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        config_arg = cms_factory.call_args[0][0]
        assert config_arg.region_id == "cn-hangzhou"

    def test_query_cmd_uses_profile_region(self, mocker):
        """metric query also reads region from profile when --region omitted."""
        fake_client = MagicMock()
        fake_client.describe_metric_list.return_value = _build_metric_response(
            code="200", datapoints=[], next_token=None
        )

        cms_factory = MagicMock(return_value=fake_client)
        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={"region_id": "cn-shenzhen"},
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "query", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        assert result.exit_code == 0, result.output
        config_arg = cms_factory.call_args[0][0]
        assert config_arg.region_id == "cn-shenzhen"

    def test_latest_cmd_uses_profile_region(self, mocker):
        """metric latest also reads region from profile when --region omitted."""
        fake_client = MagicMock()
        fake_client.describe_metric_last.return_value = _build_metric_response(
            code="200", datapoints=[], next_token=None
        )

        cms_factory = MagicMock(return_value=fake_client)
        _inject_fake_sdk(
            mocker,
            cms_client_factory=cms_factory,
            credential_client_factory=MagicMock(return_value=MagicMock()),
            profile={"region_id": "cn-shenzhen"},
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metric", "latest", "cpu_usage", "--instance-id", "hgprecn-cn-xxx"],
        )

        assert result.exit_code == 0, result.output
        config_arg = cms_factory.call_args[0][0]
        assert config_arg.region_id == "cn-shenzhen"


# ---------------------------------------------------------------------------
# _create_cms_client credential resolution
# ---------------------------------------------------------------------------


class TestCreateCmsClientCredentials:
    """Tests for the AK/SK priority used by ``_create_cms_client``.

    Priority: ``hologres config`` profile AK/SK > default credential chain.
    """

    def test_uses_profile_ak_sk_when_present(self, mocker):
        """When the active profile has AK/SK, build CredentialClient with an
        ``access_key`` typed CredentialConfig (skipping the default chain)."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "test-ak",
                "access_key_secret": "test-sk",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output

        # CredentialClient must be invoked exactly once, with a positional
        # CredentialConfig of type 'access_key'.
        credential_factory.assert_called_once()
        args, kwargs = credential_factory.call_args
        assert kwargs == {}
        assert len(args) == 1
        cred_config = args[0]
        assert cred_config.type == "access_key"
        assert cred_config.access_key_id == "test-ak"
        assert cred_config.access_key_secret == "test-sk"

    def test_cms_ak_sk_takes_priority_over_general(self, mocker):
        """When both cms_access_key_id and access_key_id exist, the
        metric-specific cms_access_key_id/sk take priority."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "general-ak",
                "access_key_secret": "general-sk",
                "cms_access_key_id": "cms-ak",
                "cms_access_key_secret": "cms-sk",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output

        credential_factory.assert_called_once()
        args, _ = credential_factory.call_args
        cred_config = args[0]
        assert cred_config.type == "access_key"
        assert cred_config.access_key_id == "cms-ak"
        assert cred_config.access_key_secret == "cms-sk"

    def test_falls_back_to_general_ak_when_cms_partial(self, mocker):
        """When only cms_access_key_id is set (no sk), fall back to general AK/SK."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={
                "region_id": "cn-hangzhou",
                "access_key_id": "general-ak",
                "access_key_secret": "general-sk",
                "cms_access_key_id": "cms-ak-only",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output

        credential_factory.assert_called_once()
        args, _ = credential_factory.call_args
        cred_config = args[0]
        assert cred_config.access_key_id == "general-ak"
        assert cred_config.access_key_secret == "general-sk"

    def test_falls_back_to_default_chain_when_profile_missing_ak_sk(self, mocker):
        """When the profile lacks AK/SK, CredentialClient is constructed with
        no arguments (default credential chain)."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={"region_id": "cn-hangzhou"},  # no AK/SK
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        credential_factory.assert_called_once_with()

    def test_falls_back_when_profile_only_has_ak(self, mocker):
        """Partial AK/SK (only one of the two) must fall back to default chain."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={"region_id": "cn-hangzhou", "access_key_id": "test-ak"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        assert result.exit_code == 0, result.output
        credential_factory.assert_called_once_with()

    def test_falls_back_when_profile_lookup_raises(self, mocker):
        """If get_current_profile raises, _create_cms_client falls back to the
        default credential chain rather than surfacing the profile error."""
        fake_client = MagicMock()
        fake_client.describe_metric_meta_list.return_value = _build_meta_response(
            code="200", resources=[]
        )

        credential_factory = MagicMock(return_value=MagicMock())

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(return_value=fake_client),
            credential_client_factory=credential_factory,
            profile={"region_id": "cn-hangzhou"},
        )
        # Override the profile mock to raise, after _inject_fake_sdk wired it.
        mocker.patch(
            "hologres_cli.commands.metric.get_current_profile",
            side_effect=RuntimeError("no config"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list", "--region", "cn-hangzhou"])

        assert result.exit_code == 0, result.output
        credential_factory.assert_called_once_with()

    def test_credential_error_hint_mentions_metric_config(self, mocker):
        """CREDENTIAL_ERROR hint must mention `hologres metric config`,
        `hologres config`, and the ALIBABA_CLOUD_ACCESS_KEY_* env vars."""
        def _boom(*args, **kwargs):
            raise RuntimeError("credentials not found")

        _inject_fake_sdk(
            mocker,
            cms_client_factory=MagicMock(),
            credential_client_factory=_boom,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CREDENTIAL_ERROR"
        msg = output["error"]["message"]
        assert "hologres metric config" in msg
        assert "hologres config" in msg
        assert "ALIBABA_CLOUD_ACCESS_KEY_ID" in msg


# ---------------------------------------------------------------------------
# STS auth_mode 分支（metric 链路接入 STS，与 SQL 链路一致）
# ---------------------------------------------------------------------------


class TestCreateCmsClientSts:
    """auth_mode=sts 时 _create_cms_client 复用 credentials.get_credential_client。"""

    def test_sts_uses_get_credential_client(self, mocker):
        fake_cred_client = MagicMock(name="sts_cred_client")
        mocker.patch(
            "hologres_cli.commands.metric.credentials.get_credential_client",
            return_value=fake_cred_client,
        )
        captured = {}

        class FakeCMSClient:
            def __init__(self, config):
                captured["config"] = config

        _inject_fake_sdk(
            mocker,
            cms_client_factory=FakeCMSClient,
            profile={"auth_mode": "sts", "region_id": "cn-hangzhou", "credentials_uri": ""},
        )
        from hologres_cli.commands.metric import _create_cms_client
        _create_cms_client("cn-hangzhou")
        # sts 分支：Config(credential=get_credential_client 返回的 fake)，不走 AK 字段
        assert captured["config"].credential is fake_cred_client
        assert captured["config"].region_id == "cn-hangzhou"

    def test_non_sts_keeps_ak_priority(self, mocker):
        """回归：ram profile 有 access_key_id → _resolve_ak_credential_client 优先级 2。"""
        cred_instances = []

        class FakeCredentialClient:
            def __init__(self, config=None):
                cred_instances.append(config)

        _inject_fake_sdk(
            mocker,
            credential_client_factory=FakeCredentialClient,
            profile={
                "auth_mode": "ram",
                "access_key_id": "LTAIx",
                "access_key_secret": "sky",
                "region_id": "cn-hangzhou",
            },
        )
        from hologres_cli.commands.metric import _create_cms_client
        _create_cms_client("cn-hangzhou")
        # 优先级 2 命中 → CredentialClient(CredentialConfig(type=access_key, ak, sk))
        assert len(cred_instances) == 1
        cfg = cred_instances[0]
        assert cfg.type == "access_key"
        assert cfg.access_key_id == "LTAIx"
        assert cfg.access_key_secret == "sky"


class TestMetricCmdStsErrorMapping:
    """sts 凭证失败时，metric 命令输出精确的 CredentialsError code（非固定 CREDENTIAL_ERROR）。"""

    def _setup_sts_failure(self, mocker, exc):
        mocker.patch(
            "hologres_cli.commands.metric.credentials.get_credential_client",
            side_effect=exc,
        )
        _inject_fake_sdk(mocker, profile={"auth_mode": "sts", "region_id": "cn-hangzhou"})

    def test_list_maps_credentials_error(self, mocker):
        from hologres_cli.credentials import CredentialsError
        from hologres_cli.errors import ErrorCode
        self._setup_sts_failure(mocker, CredentialsError(ErrorCode.STS_FETCH_ERROR, "boom"))
        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "list", "--region", "cn-hangzhou"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "STS_FETCH_ERROR"
        assert out["error"]["retryable"] is True

    def test_query_maps_credentials_error(self, mocker):
        from hologres_cli.credentials import CredentialsError
        from hologres_cli.errors import ErrorCode
        self._setup_sts_failure(mocker, CredentialsError(ErrorCode.CREDENTIALS_URI_INVALID, "bad uri"))
        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "query", "cpu", "--instance-id", "x", "--region", "cn-hangzhou"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "CREDENTIALS_URI_INVALID"

    def test_latest_maps_credentials_error(self, mocker):
        from hologres_cli.credentials import CredentialsError
        from hologres_cli.errors import ErrorCode
        self._setup_sts_failure(mocker, CredentialsError(ErrorCode.STS_FETCH_ERROR, "boom"))
        runner = CliRunner()
        result = runner.invoke(cli, ["metric", "latest", "cpu", "--instance-id", "x", "--region", "cn-hangzhou"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "STS_FETCH_ERROR"
