"""Tests for AI commands."""

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.unit
class TestAiGenCmd:
    """Tests for 'hologres ai gen' command."""

    def test_gen_success_no_model(self, mock_get_connection):
        """ai gen without --model uses single-param ai_gen(prompt)."""
        mock_get_connection.execute.return_value = [{"ai_gen": "Hologres 是一款..."}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "介绍下 hologres"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["text"] == "Hologres 是一款..."
        assert "model" not in output["data"]
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s)"
        assert call_args[0][1] == ("介绍下 hologres",)
        mock_get_connection.close.assert_called_once()

    def test_gen_success_with_model(self, mock_get_connection):
        """ai gen with --model uses two-param ai_gen(model, prompt)."""
        mock_get_connection.execute.return_value = [{"ai_gen": "generated text"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello", "--model", "qwen-plus"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["text"] == "generated text"
        assert output["data"]["model"] == "qwen-plus"
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s, %s)"
        assert call_args[0][1] == ("qwen-plus", "hello")

    def test_gen_success_table_format(self, mock_get_connection):
        """ai gen with table format outputs plain text."""
        mock_get_connection.execute.return_value = [{"ai_gen": "plain text response"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "ai", "gen", "hello"])
        assert result.exit_code == 0
        assert "plain text response" in result.output

    def test_gen_connection_error(self, mocker):
        """ai gen handles connection error gracefully."""
        from hologres_cli.connection import DSNError
        mocker.patch("hologres_cli.commands.ai.get_connection",
                     side_effect=DSNError("No profile configured"))
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_gen_query_error(self, mock_get_connection):
        """ai gen handles SQL execution error."""
        mock_get_connection.execute.side_effect = Exception(
            "function ai_gen(text) does not exist"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_gen_empty_result(self, mock_get_connection):
        """ai gen handles empty result from ai_gen()."""
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["text"] == ""

    def test_gen_null_result(self, mock_get_connection):
        """ai gen handles NULL return from ai_gen()."""
        mock_get_connection.execute.return_value = [{"ai_gen": None}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["text"] == ""

    def test_gen_parameterized_query_prevents_injection(self, mock_get_connection):
        """ai gen uses parameterized query to prevent SQL injection."""
        mock_get_connection.execute.return_value = [{"ai_gen": "safe"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "'; DROP TABLE users; --"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s)"
        assert call_args[0][1] == ("'; DROP TABLE users; --",)

    def test_gen_special_characters_in_prompt(self, mock_get_connection):
        """ai gen handles special characters in prompt."""
        mock_get_connection.execute.return_value = [{"ai_gen": "ok"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", '包含"引号"的文本'])
        assert result.exit_code == 0

    def test_gen_short_model_flag(self, mock_get_connection):
        """ai gen accepts -m as short form for --model."""
        mock_get_connection.execute.return_value = [{"ai_gen": "text"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen", "hello", "-m", "qwen-turbo"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["model"] == "qwen-turbo"

    def test_gen_missing_prompt_argument(self):
        """ai gen shows error when prompt argument is missing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "gen"])
        assert result.exit_code != 0
