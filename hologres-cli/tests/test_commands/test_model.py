"""Tests for model command module."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli

MOCK_MODELS = [
    {"model_name": "embed11", "model_type": "qwen3-vl-embedding", "model_provider": "bailian", "task": "embedding"},
    {"model_name": "embed12", "model_type": "qwen3-vl-embedding", "model_provider": "bailian", "task": "embedding"},
    {"model_name": "happyhorse-1_0-t2v", "model_type": "happyhorse-1.0-t2v", "model_provider": "bailian", "task": "video-generation"},
]


class TestModelListCmd:
    """Tests for model list command."""

    def test_list_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 3
        assert output["data"]["count"] == 3
        assert output["data"]["rows"][0]["model_name"] == "embed11"
        mock_get_connection.close.assert_called_once()

    def test_list_empty(self, mock_get_connection):
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_filter_by_task(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--task", "embedding"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2
        for row in output["data"]["rows"]:
            assert row["task"] == "embedding"

    def test_list_filter_by_model_type(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--model-type", "happyhorse-1.0-t2v"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 1
        assert output["data"]["rows"][0]["model_name"] == "happyhorse-1_0-t2v"

    def test_list_filter_no_match(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--task", "nonexistent"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_connection_error(self, mocker):
        mocker.patch("hologres_cli.commands.model.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_list_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_list_table_format(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "model", "list"])

        assert result.exit_code == 0
        assert "embed11" in result.output
        assert "qwen3-vl-embedding" in result.output
        assert "bailian" in result.output
