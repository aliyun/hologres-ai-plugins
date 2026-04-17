"""Integration tests for instance command with real Hologres database."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestInstanceLive:
    """Integration tests for instance command."""

    def test_instance_info(self, integration_dsn):
        """Test instance shows version and max connections."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--dsn", integration_dsn, "instance", "test_instance"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "hg_version" in output["data"]
        assert "max_connections" in output["data"]
        assert output["data"]["instance"] == "test_instance"

    def test_instance_table_format(self, integration_dsn):
        """Test instance with table format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "table", "instance", "test_instance"],
        )

        assert result.exit_code == 0
