"""Tests for volume command module."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


def _make_config(volumes=None, current="default"):
    """Helper to create a config dict with optional volumes."""
    profile = {"name": "default", "region_id": "cn-hangzhou", "database": "testdb"}
    if volumes is not None:
        profile["volumes"] = volumes
    return {"current": current, "profiles": [profile]}


def _make_config_multi(volumes=None):
    """Helper to create a config dict with two profiles."""
    p1 = {"name": "default", "region_id": "cn-hangzhou", "database": "testdb"}
    p2 = {"name": "prod", "region_id": "cn-shanghai", "database": "proddb"}
    if volumes is not None:
        p2["volumes"] = volumes
    return {"current": "default", "profiles": [p1, p2]}


# Common valid args for create
_VALID_CREATE_ARGS = [
    "volume", "create", "my_vol",
    "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
    "--root", "oss://bucket/path/",
    "--rolearn", "acs:ram::123456:role/TestRole",
]


class TestVolumeCreateCmd:
    """Tests for volume create command."""

    def test_create_success(self, mocker):
        """Test successful volume creation."""
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["volume"] == "my_vol"
        assert output["data"]["created"] is True

        # Verify volume was added to config
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        volumes = saved_config["profiles"][0]["volumes"]
        assert len(volumes) == 1
        assert volumes[0]["name"] == "my_vol"
        assert volumes[0]["type"] == "oss"
        assert volumes[0]["endpoint"] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert volumes[0]["root"] == "oss://bucket/path/"
        assert volumes[0]["rolearn"] == "acs:ram::123456:role/TestRole"

    def test_create_default_type_oss(self, mocker):
        """Test that --type defaults to 'oss' when not specified."""
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        # No --type flag
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "acs:ram::123456:role/TestRole",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

        saved_config = mock_save.call_args[0][0]
        assert saved_config["profiles"][0]["volumes"][0]["type"] == "oss"

    def test_create_invalid_name_digit_start(self, mocker):
        """Test volume name starting with digit is rejected."""
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "123vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_invalid_name_special_chars(self, mocker):
        """Test volume name with special characters is rejected."""
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my-vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_unsupported_type(self, mocker):
        """Test unsupported volume type is rejected."""
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol", "--type", "s3",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "s3" in output["error"]["message"]

    def test_create_invalid_endpoint_not_internal(self, mocker):
        """Test non-internal endpoint is rejected."""
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "internal" in output["error"]["message"].lower()

    def test_create_invalid_root_no_oss_prefix(self, mocker):
        """Test root path without oss:// prefix is rejected."""
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "/local/path/",
            "--rolearn", "arn",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "oss://" in output["error"]["message"]

    def test_create_root_auto_append_slash(self, mocker):
        """Test root path without trailing slash gets one appended."""
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path",
            "--rolearn", "arn",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

        saved_config = mock_save.call_args[0][0]
        assert saved_config["profiles"][0]["volumes"][0]["root"] == "oss://bucket/path/"

    def test_create_duplicate_name(self, mocker):
        """Test creating volume with existing name is rejected."""
        existing_vol = {
            "name": "my_vol", "type": "oss",
            "endpoint": "oss-cn-hangzhou-internal.aliyuncs.com",
            "root": "oss://bucket/path/", "rolearn": "arn",
        }
        config = _make_config(volumes=[existing_vol])
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "ALREADY_EXISTS"

    def test_create_no_profile(self, mocker):
        """Test create with no current profile configured."""
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_create_with_profile_flag(self, mocker):
        """Test create with --profile flag targets correct profile."""
        config = _make_config_multi()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", "prod",
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

        # Verify volume was added to prod profile (index 1)
        saved_config = mock_save.call_args[0][0]
        assert "volumes" not in saved_config["profiles"][0]  # default has no volumes
        assert len(saved_config["profiles"][1]["volumes"]) == 1
        assert saved_config["profiles"][1]["volumes"][0]["name"] == "my_vol"

    def test_create_table_format(self, mocker):
        """Test create with table format output."""
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--format", "table",
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
        ])

        assert result.exit_code == 0
        assert "my_vol" in result.output


class TestVolumeListCmd:
    """Tests for volume list command."""

    def test_list_empty(self, mocker):
        """Test list with no volumes configured."""
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_with_volumes(self, mocker):
        """Test list with existing volumes."""
        volumes = [
            {"name": "vol1", "type": "oss", "endpoint": "ep1", "root": "oss://b1/", "rolearn": "arn1"},
            {"name": "vol2", "type": "oss", "endpoint": "ep2", "root": "oss://b2/", "rolearn": "arn2"},
        ]
        config = _make_config(volumes=volumes)
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2
        rows = output["data"]["rows"]
        assert rows[0]["name"] == "vol1"
        assert rows[1]["name"] == "vol2"
        # rolearn should not be in list output
        assert "rolearn" not in rows[0]

    def test_list_no_profile(self, mocker):
        """Test list with no current profile configured."""
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_list_table_format(self, mocker):
        """Test list with table format output."""
        volumes = [
            {"name": "vol1", "type": "oss", "endpoint": "ep1", "root": "oss://b1/", "rolearn": "arn1"},
        ]
        config = _make_config(volumes=volumes)
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "volume", "list"])

        assert result.exit_code == 0
        assert "vol1" in result.output

    def test_list_csv_format(self, mocker):
        """Test list with CSV format output."""
        volumes = [
            {"name": "vol1", "type": "oss", "endpoint": "ep1", "root": "oss://b1/", "rolearn": "arn1"},
        ]
        config = _make_config(volumes=volumes)
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "volume", "list"])

        assert result.exit_code == 0
        assert "vol1" in result.output
        assert "name" in result.output


class TestVolumeDeleteCmd:
    """Tests for volume delete command."""

    def test_delete_success(self, mocker):
        """Test successful volume deletion."""
        volumes = [
            {"name": "vol1", "type": "oss", "endpoint": "ep1", "root": "oss://b1/", "rolearn": "arn1"},
            {"name": "vol2", "type": "oss", "endpoint": "ep2", "root": "oss://b2/", "rolearn": "arn2"},
        ]
        config = _make_config(volumes=volumes)
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "vol1"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["volume"] == "vol1"
        assert output["data"]["deleted"] is True

        # Verify vol1 was removed
        saved_config = mock_save.call_args[0][0]
        remaining = saved_config["profiles"][0]["volumes"]
        assert len(remaining) == 1
        assert remaining[0]["name"] == "vol2"

    def test_delete_not_found(self, mocker):
        """Test deleting a non-existent volume."""
        config = _make_config(volumes=[])
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_delete_no_profile(self, mocker):
        """Test delete with no current profile configured."""
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "vol1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_delete_profile_without_volumes_field(self, mocker):
        """Test delete when profile has no volumes field at all."""
        config = _make_config()  # No volumes field
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "vol1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"
