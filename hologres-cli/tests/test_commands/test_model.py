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

    def test_list_connection_error(self, monkeypatch):
        def _raise(**kw):
            raise DSNError("No DSN configured")
        monkeypatch.setattr("hologres_cli.commands.model.get_connection", _raise)

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

    def test_list_search_matches_model_type(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--search", "happy"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 1
        assert output["data"]["rows"][0]["model_type"] == "happyhorse-1.0-t2v"

    def test_list_search_matches_model_name_only(self, mock_get_connection):
        disjoint = [
            {"model_name": "happy_alias", "model_type": "qwen3-max",
             "model_provider": "bailian", "task": "chat/completions"},
            {"model_name": "video_alias", "model_type": "happyhorse-1.0-i2v",
             "model_provider": "bailian", "task": "video-generation"},
            {"model_name": "embed11", "model_type": "qwen3-vl-embedding",
             "model_provider": "bailian", "task": "embedding"},
        ]
        mock_get_connection.execute.return_value = disjoint

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--search", "happy"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 2
        names = {r["model_name"] for r in output["data"]["rows"]}
        assert names == {"happy_alias", "video_alias"}

    def test_list_search_case_insensitive(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        upper = runner.invoke(cli, ["model", "list", "--search", "HAPPY"])
        lower = runner.invoke(cli, ["model", "list", "--search", "happy"])

        assert upper.exit_code == 0 and lower.exit_code == 0
        assert json.loads(upper.output) == json.loads(lower.output)
        assert json.loads(upper.output)["data"]["count"] == 1

    def test_list_search_no_match(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--search", "xyz_nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_search_combined_with_task(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "list",
            "--task", "video-generation",
            "--search", "happy",
        ])

        output = json.loads(result.output)
        assert output["data"]["count"] == 1
        assert output["data"]["rows"][0]["task"] == "video-generation"
        assert output["data"]["rows"][0]["model_type"] == "happyhorse-1.0-t2v"

    def test_list_search_combined_with_model_type(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        hit = runner.invoke(cli, [
            "model", "list",
            "--model-type", "happyhorse-1.0-t2v",
            "--search", "happy",
        ])
        assert json.loads(hit.output)["data"]["count"] == 1

        miss = runner.invoke(cli, [
            "model", "list",
            "--model-type", "qwen3-vl-embedding",
            "--search", "happy",
        ])
        assert json.loads(miss.output)["data"]["count"] == 0


class TestModelCatalogNotSupported:
    """Tests for model catalog command (not supported)."""

    def test_catalog_returns_not_supported(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_SUPPORTED"
        assert "not supported" in output["error"]["message"]

    def test_catalog_not_supported_table_format(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "model", "catalog"])

        assert result.exit_code == 0
        assert "not supported" in result.output.lower()


class TestModelDeleteCmd:
    """Tests for model delete command."""

    def test_delete_dry_run_default(self, mock_get_connection):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert output["data"]["model"] == "embed11"
        assert "sql" not in output["data"]
        mock_get_connection.execute.assert_not_called()

    def test_delete_with_confirm_executes(self, mock_get_connection):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["model"] == "embed11"
        assert output["data"]["deleted"] is True
        mock_get_connection.execute.assert_called_once_with(
            "CALL delete_external_model('embed11')"
        )
        mock_get_connection.close.assert_called_once()

    def test_delete_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception(
            "external model 'embed11' does not exist"
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_delete_connection_error(self, monkeypatch):
        def _raise(**kw):
            raise DSNError("No DSN configured")
        monkeypatch.setattr("hologres_cli.commands.model.get_connection", _raise)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    @pytest.mark.parametrize("bad_name", [
        "name';DROP TABLE x;--",
        "with space",
        "semi;colon",
        "中文名",
        "name@host",
        "name/slash",
        "",
    ])
    def test_delete_invalid_name_rejected(self, mock_get_connection, bad_name):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", bad_name])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"
        mock_get_connection.execute.assert_not_called()

    @pytest.mark.parametrize("good_name", [
        "embed11",
        "qwen3-vl-embedding",
        "happyhorse-1.0-t2v",
        "a.b_c-d",
    ])
    def test_delete_accepts_valid_names(self, mock_get_connection, good_name):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", good_name])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["model"] == good_name
        assert output["data"]["dry_run"] is True

    def test_delete_dry_run_does_not_connect(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "hologres_cli.commands.model.get_connection",
            lambda **kw: called.append(1),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert called == []


class TestModelCreateNotSupported:
    """Tests for model create command (not supported)."""

    def test_create_returns_not_supported(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["model", "create"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_SUPPORTED"
        assert "not supported" in output["error"]["message"]

    def test_create_not_supported_does_not_connect(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "hologres_cli.commands.model.get_connection",
            lambda **kw: called.append(1),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "create"])

        assert result.exit_code == 0
        assert called == []
