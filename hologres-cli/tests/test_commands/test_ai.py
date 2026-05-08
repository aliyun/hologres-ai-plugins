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


@pytest.mark.unit
class TestAiImageGenCmd:
    """Tests for 'hologres ai image-gen' command."""

    MOCK_RESPONSE = json.dumps({
        "requestId": "6dace24e-7f2d-4ec2-a8ac-aa73415a35a8",
        "usage": {"height": 720, "image_count": 1, "width": 1280},
        "image_urls": ["https://dashscope-xxx.oss.aliyuncs.com/7d/69/c58b7714-b147.png?Expires=123"],
        "image_oss_paths": []
    })

    MOCK_RESPONSE_MULTI = json.dumps({
        "requestId": "abc-123",
        "usage": {"height": 720, "image_count": 2, "width": 1280},
        "image_urls": [
            "https://dashscope-xxx.oss.aliyuncs.com/7d/69/img-aaa.png?Expires=123",
            "https://dashscope-xxx.oss.aliyuncs.com/7d/69/img-bbb.png?Expires=456",
        ],
        "image_oss_paths": []
    })

    @staticmethod
    def _mock_urlopen(mocker, side_effect=None):
        """Helper to mock urllib.request.urlopen with a context-manager response."""
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = b"\x89PNG fake image data"
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mock_open = mocker.patch("urllib.request.urlopen")
        if side_effect:
            mock_open.side_effect = side_effect
        else:
            mock_open.return_value = mock_resp
        return mock_open

    def test_image_gen_minimal(self, mock_get_connection, tmp_path, mocker):
        """image-gen downloads image and returns local path with filename from URL."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "生成一只猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["images"]) == 1
        assert output["data"]["images"][0].endswith("c58b7714-b147.png")
        assert str(tmp_path) in output["data"]["images"][0]
        assert output["data"]["usage"] == {"height": 720, "image_count": 1, "width": 1280}
        assert "model" not in output["data"]
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s)"
        request = json.loads(call_args[0][1][0])
        assert request["prompt"] == "生成一只猫"
        assert "parameters" not in request
        mock_get_connection.close.assert_called_once()

    def test_image_gen_with_model(self, mock_get_connection, tmp_path, mocker):
        """image-gen with --model uses two-param ai_gen()."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-m", "qwen-image-2.0", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["model"] == "qwen-image-2.0"
        assert len(output["data"]["images"]) == 1
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s, %s)"
        assert call_args[0][1][0] == "qwen-image-2.0"

    def test_image_gen_multiple_images(self, mock_get_connection, tmp_path, mocker):
        """image-gen with n>1 downloads multiple images with filenames from URLs."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE_MULTI}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-n", "2", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["data"]["images"]) == 2
        assert output["data"]["images"][0].endswith("img-aaa.png")
        assert output["data"]["images"][1].endswith("img-bbb.png")
        assert output["data"]["usage"]["image_count"] == 2

    def test_image_gen_download_creates_dir(self, mock_get_connection, tmp_path, mocker):
        """image-gen creates download dir if not exists."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        new_dir = str(tmp_path / "subdir" / "images")
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", new_dir])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert new_dir in output["data"]["images"][0]

    def test_image_gen_download_failure(self, mock_get_connection, tmp_path, mocker):
        """image-gen handles download failure gracefully."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE_MULTI}]
        # First call succeeds, second raises
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = b"\x89PNG fake"
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mock_open = mocker.patch("urllib.request.urlopen")
        mock_open.side_effect = [mock_resp, Exception("Network error")]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["images"][0] is not None
        assert output["data"]["images"][1] is None
        assert len(output["data"]["errors"]) == 1
        assert output["data"]["errors"][0]["index"] == 2

    def test_image_gen_with_all_options(self, mock_get_connection, tmp_path, mocker):
        """image-gen with all options builds complete JSON."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫",
            "--model", "qwen-image-2.0",
            "--negative-prompt", "低画质",
            "--size", "1280*720",
            "-n", "2",
            "--prompt-extend", "false",
            "--watermark", "true",
            "--seed", "42",
            "-d", str(tmp_path),
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][1])
        assert request["prompt"] == "猫"
        assert request["negative_prompt"] == "低画质"
        assert request["parameters"]["size"] == "1280*720"
        assert request["parameters"]["n"] == 2
        assert request["parameters"]["prompt_extend"] is False
        assert request["parameters"]["watermark"] is True
        assert request["parameters"]["seed"] == 42

    def test_image_gen_partial_options(self, mock_get_connection, tmp_path, mocker):
        """image-gen with partial options only includes specified params."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "--size", "1280*720", "-n", "3", "-d", str(tmp_path)])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["prompt"] == "猫"
        assert request["parameters"]["size"] == "1280*720"
        assert request["parameters"]["n"] == 3
        assert "negative_prompt" not in request
        assert "prompt_extend" not in request["parameters"]

    def test_image_gen_negative_prompt_only(self, mock_get_connection, tmp_path, mocker):
        """negative_prompt is at top level, not inside parameters."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "--negative-prompt", "模糊", "-d", str(tmp_path)])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["negative_prompt"] == "模糊"
        assert "parameters" not in request

    def test_image_gen_table_format(self, mock_get_connection, tmp_path, mocker):
        """image-gen with table format outputs local paths, one per line."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE_MULTI}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert str(tmp_path) in result.output
        assert "img-aaa.png" in result.output
        assert "img-bbb.png" in result.output

    def test_image_gen_json_parse_failure_fallback(self, mock_get_connection, tmp_path):
        """image-gen falls back to raw_result when response is not valid JSON."""
        mock_get_connection.execute.return_value = [{"ai_gen": "not-json-response"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == "not-json-response"
        assert "images" not in output["data"]

    def test_image_gen_no_image_urls_field_fallback(self, mock_get_connection, tmp_path):
        """image-gen falls back when JSON has no image_urls field."""
        mock_get_connection.execute.return_value = [{"ai_gen": '{"requestId": "abc", "other": 1}'}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["raw_result"] == '{"requestId": "abc", "other": 1}'

    def test_image_gen_connection_error(self, mocker, tmp_path):
        """image-gen handles connection error gracefully."""
        from hologres_cli.connection import DSNError
        mocker.patch("hologres_cli.commands.ai.get_connection",
                     side_effect=DSNError("No profile configured"))
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_image_gen_query_error(self, mock_get_connection, tmp_path):
        """image-gen handles SQL execution error."""
        mock_get_connection.execute.side_effect = Exception("model not supported")
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_image_gen_empty_result(self, mock_get_connection, tmp_path):
        """image-gen handles empty result."""
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == ""

    def test_image_gen_null_result(self, mock_get_connection, tmp_path):
        """image-gen handles NULL return."""
        mock_get_connection.execute.return_value = [{"ai_gen": None}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-d", str(tmp_path)])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["raw_result"] == ""

    def test_image_gen_parameterized_query(self, mock_get_connection, tmp_path, mocker):
        """image-gen uses parameterized query to prevent SQL injection."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "'; DROP TABLE users; --", "-d", str(tmp_path)])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s)"

    def test_image_gen_missing_prompt(self, tmp_path):
        """image-gen shows error when prompt is missing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "-d", str(tmp_path)])
        assert result.exit_code != 0

    def test_image_gen_missing_download_dir(self):
        """image-gen shows error when --download-dir is missing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫"])
        assert result.exit_code != 0

    def test_image_gen_prompt_extend_case_insensitive(self, mock_get_connection, tmp_path, mocker):
        """--prompt-extend accepts True/False case-insensitively."""
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        self._mock_urlopen(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "--prompt-extend", "True", "-d", str(tmp_path)])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["parameters"]["prompt_extend"] is True

    def test_image_gen_invalid_n_type(self, tmp_path):
        """-n with non-integer value should fail."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-n", "abc", "-d", str(tmp_path)])
        assert result.exit_code != 0
