"""Tests for volume command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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


def _vol_entry(name="my_vol", **overrides):
    """Build a volume entry dict with all required fields."""
    entry = {
        "name": name,
        "type": "oss",
        "endpoint": "oss-cn-hangzhou-internal.aliyuncs.com",
        "public_endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "root": "oss://bucket/path/",
        "rolearn": "acs:ram::123456:role/TestRole",
        "access_key": "LTAI5tTestAK",
        "access_secret": "TestSecretXXX",
    }
    entry.update(overrides)
    return entry


# Common valid args for create (now includes --access-key and --access-secret)
_VALID_CREATE_ARGS = [
    "volume", "create", "my_vol",
    "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
    "--root", "oss://bucket/path/",
    "--rolearn", "acs:ram::123456:role/TestRole",
    "--access-key", "LTAI5tTestAK",
    "--access-secret", "TestSecretXXX",
]


def _mock_oss_client(mocker):
    """Mock _get_oss_client to return a fake bucket with no-op put_object."""
    mock_bucket = MagicMock()
    mocker.patch(
        "hologres_cli.commands.volume._get_oss_client",
        return_value=(mock_bucket, "path/"),
    )
    return mock_bucket


class TestVolumeCreateCmd:
    """Tests for volume create command."""

    def test_create_success(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")
        mock_bucket = _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["volume"] == "my_vol"
        assert output["data"]["created"] is True

        mock_bucket.put_object.assert_called_once_with("path/", b"")

        saved_config = mock_save.call_args[0][0]
        vol = saved_config["profiles"][0]["volumes"][0]
        assert vol["name"] == "my_vol"
        assert vol["type"] == "oss"
        assert vol["endpoint"] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert vol["root"] == "oss://bucket/path/"
        assert vol["rolearn"] == "acs:ram::123456:role/TestRole"
        assert vol["access_key"] == "LTAI5tTestAK"
        assert vol["access_secret"] == "TestSecretXXX"

    def test_create_oss_failure_aborts(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        mock_bucket = MagicMock()
        mock_bucket.put_object.side_effect = Exception("Access denied")
        mocker.patch(
            "hologres_cli.commands.volume._get_oss_client",
            return_value=(mock_bucket, "path/"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"
        mock_save.assert_not_called()

    def test_create_empty_prefix_skips_oss_put(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")

        mock_bucket = MagicMock()
        mocker.patch(
            "hologres_cli.commands.volume._get_oss_client",
            return_value=(mock_bucket, ""),
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        mock_bucket.put_object.assert_not_called()
        mock_save.assert_called_once()

    def test_create_public_endpoint_auto_generated(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")
        _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        assert result.exit_code == 0
        saved_config = mock_save.call_args[0][0]
        vol = saved_config["profiles"][0]["volumes"][0]
        assert vol["public_endpoint"] == "oss-cn-hangzhou.aliyuncs.com"

    def test_create_missing_access_key(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-secret", "secret",
        ])
        assert result.exit_code != 0
        assert "access-key" in result.output.lower()

    def test_create_missing_access_secret(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak",
        ])
        assert result.exit_code != 0
        assert "access-secret" in result.output.lower()

    def test_create_default_type_oss(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")
        _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        assert result.exit_code == 0
        saved_config = mock_save.call_args[0][0]
        assert saved_config["profiles"][0]["volumes"][0]["type"] == "oss"

    def test_create_invalid_name_digit_start(self, mocker):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "123vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_invalid_name_special_chars(self, mocker):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my-vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_unsupported_type(self, mocker):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol", "--type", "s3",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "s3" in output["error"]["message"]

    def test_create_invalid_endpoint_not_internal(self, mocker):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "internal" in output["error"]["message"].lower()

    def test_create_invalid_root_no_oss_prefix(self, mocker):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=_make_config())
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "/local/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "oss://" in output["error"]["message"]

    def test_create_root_auto_append_slash(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")
        _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        assert result.exit_code == 0
        saved_config = mock_save.call_args[0][0]
        assert saved_config["profiles"][0]["volumes"][0]["root"] == "oss://bucket/path/"

    def test_create_duplicate_name(self, mocker):
        existing_vol = _vol_entry()
        config = _make_config(volumes=[existing_vol])
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "ALREADY_EXISTS"

    def test_create_no_profile(self, mocker):
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, _VALID_CREATE_ARGS)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_create_with_profile_flag(self, mocker):
        config = _make_config_multi()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mock_save = mocker.patch("hologres_cli.commands.volume.save_config")
        _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", "prod",
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

        saved_config = mock_save.call_args[0][0]
        assert "volumes" not in saved_config["profiles"][0]
        assert len(saved_config["profiles"][1]["volumes"]) == 1
        assert saved_config["profiles"][1]["volumes"][0]["name"] == "my_vol"

    def test_create_table_format(self, mocker):
        config = _make_config()
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")
        _mock_oss_client(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--format", "table",
            "volume", "create", "my_vol",
            "--endpoint", "oss-cn-hangzhou-internal.aliyuncs.com",
            "--root", "oss://bucket/path/",
            "--rolearn", "arn",
            "--access-key", "ak", "--access-secret", "sk",
        ])

        assert result.exit_code == 0
        assert "my_vol" in result.output


class TestVolumeListCmd:
    """Tests for volume list command."""

    def test_list_empty(self, mocker):
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
        volumes = [
            _vol_entry("vol1"),
            _vol_entry("vol2", endpoint="ep2", root="oss://b2/"),
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
        # Sensitive fields should not be in list output
        assert "rolearn" not in rows[0]
        assert "access_key" not in rows[0]
        assert "access_secret" not in rows[0]

    def test_list_no_profile(self, mocker):
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_list_table_format(self, mocker):
        volumes = [_vol_entry("vol1")]
        config = _make_config(volumes=volumes)
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "volume", "list"])

        assert result.exit_code == 0
        assert "vol1" in result.output

    def test_list_csv_format(self, mocker):
        volumes = [_vol_entry("vol1")]
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
        volumes = [_vol_entry("vol1"), _vol_entry("vol2")]
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

        saved_config = mock_save.call_args[0][0]
        remaining = saved_config["profiles"][0]["volumes"]
        assert len(remaining) == 1
        assert remaining[0]["name"] == "vol2"

    def test_delete_not_found(self, mocker):
        config = _make_config(volumes=[])
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_delete_no_profile(self, mocker):
        config = {"current": "", "profiles": []}
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "vol1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_delete_profile_without_volumes_field(self, mocker):
        config = _make_config()  # No volumes field
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        mocker.patch("hologres_cli.commands.volume.save_config")

        runner = CliRunner()
        result = runner.invoke(cli, ["volume", "delete", "vol1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"


class TestVolumeListFilesCmd:
    """Tests for volume list-files command."""

    def _invoke(self, mocker, config, extra_args=None):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        runner = CliRunner()
        args = ["volume", "list-files", "--volume", "my_vol"]
        if extra_args:
            args.extend(extra_args)
        return runner.invoke(cli, args)

    def test_list_files_success(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        mock_obj1 = MagicMock()
        mock_obj1.key = "path/report.csv"
        mock_obj1.size = 1024
        mock_obj1.last_modified = "2026-05-01T10:00:00Z"

        mock_obj2 = MagicMock()
        mock_obj2.key = "path/data.json"
        mock_obj2.size = 512
        mock_obj2.last_modified = "2026-05-02T11:00:00Z"

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_bucket = MagicMock()
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = mock_bucket
            mock_oss2.ObjectIterator.return_value = iter([mock_obj1, mock_obj2])
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2
        assert output["data"]["rows"][0]["name"] == "report.csv"
        assert output["data"]["rows"][0]["volume_path"] == "volume://my_vol/report.csv"
        assert output["data"]["rows"][0]["oss_path"] == "oss://bucket/path/report.csv"
        assert output["data"]["rows"][1]["name"] == "data.json"
        assert output["data"]["rows"][1]["volume_path"] == "volume://my_vol/data.json"
        assert output["data"]["rows"][1]["oss_path"] == "oss://bucket/path/data.json"

    def test_list_files_with_prefix(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        mock_obj = MagicMock()
        mock_obj.key = "path/sub/file.txt"
        mock_obj.size = 100
        mock_obj.last_modified = "2026-05-01"

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.return_value = iter([mock_obj])
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--prefix", "sub/"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"][0]["name"] == "sub/file.txt"
        assert output["data"]["rows"][0]["volume_path"] == "volume://my_vol/sub/file.txt"
        assert output["data"]["rows"][0]["oss_path"] == "oss://bucket/path/sub/file.txt"

    def test_list_files_empty(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.return_value = iter([])
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 0

    def test_list_files_volume_not_found(self, mocker):
        config = _make_config(volumes=[])
        result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_list_files_oss_error(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            oss_exc = type("OssError", (Exception,), {})
            mock_oss2.exceptions.OssError = oss_exc
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.side_effect = oss_exc("Access denied")

            result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"

    def test_list_files_net_intranet(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.return_value = iter([])
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--net", "intranet"])

        assert result.exit_code == 0
        # Verify internal endpoint was used
        mock_oss2.Bucket.assert_called_once()
        call_args = mock_oss2.Bucket.call_args
        assert call_args[0][1] == "oss-cn-hangzhou-internal.aliyuncs.com"

    def test_list_files_net_internet_default(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.return_value = iter([])
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config)

        assert result.exit_code == 0
        mock_oss2.Bucket.assert_called_once()
        call_args = mock_oss2.Bucket.call_args
        assert call_args[0][1] == "oss-cn-hangzhou.aliyuncs.com"

    def test_list_files_with_max_count(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        objs = []
        for i in range(5):
            o = MagicMock()
            o.key = f"path/file{i}.txt"
            o.size = 100
            o.last_modified = "2026-05-01"
            objs.append(o)

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.ObjectIterator.return_value = iter(objs)
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--max-count", "3"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 3


class TestVolumeDeleteFileCmd:
    """Tests for volume delete-file command."""

    def _invoke(self, mocker, config, extra_args=None):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        runner = CliRunner()
        args = ["volume", "delete-file", "--volume", "my_vol", "--file", "report.csv"]
        if extra_args:
            args.extend(extra_args)
        return runner.invoke(cli, args)

    def test_delete_file_dry_run(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        result = self._invoke(mocker, config)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert output["data"]["volume_path"] == "volume://my_vol/report.csv"
        assert output["data"]["oss_path"] == "oss://bucket/path/report.csv"

    def test_delete_file_confirm(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_bucket = MagicMock()
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = mock_bucket
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["deleted"] is True
        assert output["data"]["volume_path"] == "volume://my_vol/report.csv"
        assert output["data"]["oss_path"] == "oss://bucket/path/report.csv"
        mock_bucket.delete_object.assert_called_once_with("path/report.csv")

    def test_delete_file_volume_not_found(self, mocker):
        config = _make_config(volumes=[])
        result = self._invoke(mocker, config, ["--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_delete_file_oss_error(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            oss_exc = type("OssError", (Exception,), {})
            mock_oss2.exceptions.OssError = oss_exc
            mock_oss2.Auth.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.delete_object.side_effect = oss_exc("Forbidden")
            mock_oss2.Bucket.return_value = mock_bucket

            result = self._invoke(mocker, config, ["--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"

    def test_delete_file_net_intranet(self, mocker):
        config = _make_config(volumes=[_vol_entry()])

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--confirm", "--net", "intranet"])

        assert result.exit_code == 0
        call_args = mock_oss2.Bucket.call_args
        assert call_args[0][1] == "oss-cn-hangzhou-internal.aliyuncs.com"


class TestVolumeDownloadFileCmd:
    """Tests for volume download-file command."""

    def _invoke(self, mocker, config, extra_args=None):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        runner = CliRunner()
        args = ["volume", "download-file", "--volume", "my_vol",
                "--file", "report.csv", "-d", "/tmp/test_dl"]
        if extra_args:
            args.extend(extra_args)
        return runner.invoke(cli, args)

    def test_download_file_success(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.makedirs")

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_bucket = MagicMock()
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = mock_bucket
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["downloaded"] is True
        assert output["data"]["file"] == "report.csv"
        assert output["data"]["volume_path"] == "volume://my_vol/report.csv"
        assert output["data"]["oss_path"] == "oss://bucket/path/report.csv"
        mock_bucket.get_object_to_file.assert_called_once()

    def test_download_file_volume_not_found(self, mocker):
        config = _make_config(volumes=[])
        result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_download_file_oss_error(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.makedirs")

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            oss_exc = type("OssError", (Exception,), {})
            mock_oss2.exceptions.OssError = oss_exc
            mock_oss2.Auth.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.get_object_to_file.side_effect = oss_exc("Not found")
            mock_oss2.Bucket.return_value = mock_bucket

            result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"

    def test_download_file_net_intranet(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.makedirs")

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, ["--net", "intranet"])

        assert result.exit_code == 0
        call_args = mock_oss2.Bucket.call_args
        assert call_args[0][1] == "oss-cn-hangzhou-internal.aliyuncs.com"


class TestVolumeUploadFileCmd:
    """Tests for volume upload-file command."""

    def _invoke(self, mocker, config, local_file="/tmp/data.csv", extra_args=None):
        mocker.patch("hologres_cli.commands.volume.load_config", return_value=config)
        runner = CliRunner()
        args = ["volume", "upload-file", "--volume", "my_vol",
                "--local-file", local_file, "--target-file", "data/data.csv"]
        if extra_args:
            args.extend(extra_args)
        return runner.invoke(cli, args)

    def test_upload_file_success(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.path.isfile", return_value=True)

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_bucket = MagicMock()
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = mock_bucket
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config)

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["uploaded"] is True
        assert output["data"]["target_file"] == "data/data.csv"
        assert output["data"]["volume_path"] == "volume://my_vol/data/data.csv"
        assert output["data"]["oss_path"] == "oss://bucket/path/data/data.csv"
        mock_bucket.put_object_from_file.assert_called_once_with(
            "path/data/data.csv", "/tmp/data.csv"
        )

    def test_upload_file_local_not_found(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.path.isfile", return_value=False)

        result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "FILE_NOT_FOUND"

    def test_upload_file_volume_not_found(self, mocker):
        config = _make_config(volumes=[])
        mocker.patch("os.path.isfile", return_value=True)

        result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_upload_file_oss_error(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.path.isfile", return_value=True)

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            oss_exc = type("OssError", (Exception,), {})
            mock_oss2.exceptions.OssError = oss_exc
            mock_oss2.Auth.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.put_object_from_file.side_effect = oss_exc("Permission denied")
            mock_oss2.Bucket.return_value = mock_bucket

            result = self._invoke(mocker, config)

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"

    def test_upload_file_net_intranet(self, mocker):
        config = _make_config(volumes=[_vol_entry()])
        mocker.patch("os.path.isfile", return_value=True)

        with patch("hologres_cli.commands.volume.oss2") as mock_oss2:
            mock_oss2.Auth.return_value = MagicMock()
            mock_oss2.Bucket.return_value = MagicMock()
            mock_oss2.exceptions.OssError = Exception

            result = self._invoke(mocker, config, extra_args=["--net", "intranet"])

        assert result.exit_code == 0
        call_args = mock_oss2.Bucket.call_args
        assert call_args[0][1] == "oss-cn-hangzhou-internal.aliyuncs.com"


class TestParseOssRoot:
    """Tests for _parse_oss_root helper."""

    def test_parse_bucket_and_prefix(self):
        from hologres_cli.commands.volume import _parse_oss_root
        bucket, prefix = _parse_oss_root("oss://bucket1/your/path/")
        assert bucket == "bucket1"
        assert prefix == "your/path/"

    def test_parse_bucket_only(self):
        from hologres_cli.commands.volume import _parse_oss_root
        bucket, prefix = _parse_oss_root("oss://bucket1/")
        assert bucket == "bucket1"
        assert prefix == ""

    def test_parse_nested_prefix(self):
        from hologres_cli.commands.volume import _parse_oss_root
        bucket, prefix = _parse_oss_root("oss://mybucket/a/b/c/")
        assert bucket == "mybucket"
        assert prefix == "a/b/c/"


class TestBuildPaths:
    """Tests for _build_paths helper."""

    def test_basic(self):
        from hologres_cli.commands.volume import _build_paths
        vol = {"root": "oss://bucket1/prefix/"}
        result = _build_paths("my_vol", "file.csv", vol)
        assert result["volume_path"] == "volume://my_vol/file.csv"
        assert result["oss_path"] == "oss://bucket1/prefix/file.csv"

    def test_nested_path(self):
        from hologres_cli.commands.volume import _build_paths
        vol = {"root": "oss://bucket1/a/b/"}
        result = _build_paths("vol1", "dir/sub/file.csv", vol)
        assert result["volume_path"] == "volume://vol1/dir/sub/file.csv"
        assert result["oss_path"] == "oss://bucket1/a/b/dir/sub/file.csv"
