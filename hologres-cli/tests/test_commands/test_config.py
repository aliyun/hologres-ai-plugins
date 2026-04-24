"""Tests for config CLI command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.config_store import DEFAULT_PROFILE, set_profile
from hologres_cli.main import cli


class TestConfigList:
    """Tests for config list command."""

    def test_config_list_empty(self, mock_home):
        """Test listing profiles when none configured."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []

    def test_config_list_with_profiles(self, mock_config):
        """Test listing profiles."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        assert len(rows) == 1
        assert rows[0]["name"] == "default"
        assert rows[0]["current"] == "*"


class TestConfigCurrent:
    """Tests for config current command."""

    def test_config_current_success(self, mock_config):
        """Test showing current profile."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "current"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["current"] == "default"

    def test_config_current_none(self, mock_home):
        """Test current when no profile configured."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "current"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"


class TestConfigShow:
    """Tests for config show command."""

    def test_config_show_current(self, mock_config):
        """Test showing current profile details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["name"] == "default"
        # Sensitive fields should be masked
        assert output["data"]["access_key_secret"] != "TestAccessKeySecret123"

    def test_config_show_named_profile(self, mock_config):
        """Test showing a named profile."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show", "--profile", "default"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_config_show_not_found(self, mock_config):
        """Test showing non-existent profile."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show", "--profile", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"


class TestConfigSet:
    """Tests for config set command."""

    def test_config_set_success(self, mock_config):
        """Test setting a config value."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "set", "database", "newdb"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["key"] == "database"
        assert output["data"]["value"] == "newdb"

    def test_config_set_invalid_key(self, mock_config):
        """Test setting an invalid key."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "set", "invalid_key", "value"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"

    def test_config_set_sensitive_masked(self, mock_config):
        """Test setting sensitive value shows masked output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "set", "password", "secret123"])

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["value"] == "***"


class TestConfigGet:
    """Tests for config get command."""

    def test_config_get_success(self, mock_config):
        """Test getting a config value."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get", "database"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["key"] == "database"
        assert output["data"]["value"] == "testdb"

    def test_config_get_sensitive_masked(self, mock_config):
        """Test getting sensitive value is masked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get", "access_key_secret"])

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["value"] == "***"

    def test_config_get_unknown_key(self, mock_config):
        """Test getting unknown key."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get", "nonexistent_key"])

        output = json.loads(result.output)
        assert output["ok"] is False


class TestConfigSwitch:
    """Tests for config switch command."""

    def test_config_switch_success(self, mock_config):
        """Test switching profile."""
        # Add a second profile
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "prod"
        set_profile(profile)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "switch", "prod"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["current"] == "prod"

    def test_config_switch_not_found(self, mock_config):
        """Test switching to non-existent profile."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "switch", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIG_ERROR"


class TestConfigDelete:
    """Tests for config delete command."""

    def test_config_delete_requires_confirm(self, mock_config):
        """Test delete without --confirm flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "delete", "default"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONFIRMATION_REQUIRED"

    def test_config_delete_success(self, mock_config):
        """Test deleting a profile with --confirm."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "delete", "default", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["deleted"] == "default"


class TestConfigRegistered:
    """Tests to verify config command is registered."""

    def test_config_in_help(self):
        """Test config command appears in main help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "config" in result.output
