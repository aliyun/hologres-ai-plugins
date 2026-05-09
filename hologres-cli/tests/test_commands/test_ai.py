"""Tests for AI commands."""

import json

import pytest
from click.testing import CliRunner

from hologres_cli.commands.ai import (
    _build_oss_output_dir,
    _oss_to_volume_path,
    _parse_volume_uri,
)
from hologres_cli.main import cli

SAMPLE_VOLUME_CONFIG = {
    "current": "default",
    "profiles": [{
        "name": "default",
        "volumes": [{
            "name": "test_vol",
            "type": "oss",
            "endpoint": "oss-cn-hangzhou-internal.aliyuncs.com",
            "public_endpoint": "oss-cn-hangzhou.aliyuncs.com",
            "root": "oss://mybucket/data/",
            "rolearn": "acs:ram::123456:role/AliyunHologresDefaultRole",
            "access_key": "LTAI5tXxx",
            "access_secret": "xxxx",
        }],
    }],
}


def _patch_load_config(mocker, config=None):
    """Patch load_config to return volume config."""
    mocker.patch(
        "hologres_cli.commands.ai.load_config",
        return_value=config or SAMPLE_VOLUME_CONFIG,
    )


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
class TestParseVolumeUri:
    """Tests for _parse_volume_uri."""

    def test_standard_format(self):
        assert _parse_volume_uri("volume://my_vol/sub/path") == ("my_vol", "sub/path")

    def test_no_sub_path(self):
        assert _parse_volume_uri("volume://my_vol") == ("my_vol", "")

    def test_trailing_slash(self):
        assert _parse_volume_uri("volume://my_vol/sub/") == ("my_vol", "sub/")

    def test_invalid_prefix(self):
        with pytest.raises(ValueError, match="Invalid volume URI"):
            _parse_volume_uri("oss://bucket/path")

    def test_empty_volume_name(self):
        with pytest.raises(ValueError, match="Volume name cannot be empty"):
            _parse_volume_uri("volume:///path")


@pytest.mark.unit
class TestBuildOssOutputDir:
    """Tests for _build_oss_output_dir."""

    def test_normal(self):
        assert _build_oss_output_dir("oss://bucket/path/", "sub/dir") == "oss://bucket/path/sub/dir"

    def test_root_no_trailing_slash(self):
        assert _build_oss_output_dir("oss://bucket/path", "sub/dir") == "oss://bucket/path/sub/dir"

    def test_sub_path_leading_slash(self):
        assert _build_oss_output_dir("oss://bucket/path/", "/sub/dir") == "oss://bucket/path/sub/dir"

    def test_empty_sub_path(self):
        assert _build_oss_output_dir("oss://bucket/path/", "") == "oss://bucket/path/"


@pytest.mark.unit
class TestOssToVolumePath:
    """Tests for _oss_to_volume_path."""

    def test_normal(self):
        assert _oss_to_volume_path(
            "oss://b/p/sub/img.png", "oss://b/p/", "v1"
        ) == "volume://v1/sub/img.png"

    def test_root_direct(self):
        assert _oss_to_volume_path(
            "oss://b/p/img.png", "oss://b/p/", "v1"
        ) == "volume://v1/img.png"

    def test_path_mismatch(self):
        assert _oss_to_volume_path(
            "oss://other/img.png", "oss://b/p/", "v1"
        ) == "oss://other/img.png"


@pytest.mark.unit
class TestAiImageGenCmd:
    """Tests for 'hologres ai image-gen' command."""

    MOCK_RESPONSE = json.dumps({
        "requestId": "6dace24e-7f2d-4ec2-a8ac-aa73415a35a8",
        "usage": {"height": 720, "image_count": 1, "width": 1280},
        "image_urls": [],
        "image_oss_paths": ["oss://mybucket/data/images/c58b7714-b147.png"],
    })

    MOCK_RESPONSE_MULTI = json.dumps({
        "requestId": "abc-123",
        "usage": {"height": 720, "image_count": 2, "width": 1280},
        "image_urls": [],
        "image_oss_paths": [
            "oss://mybucket/data/images/img-aaa.png",
            "oss://mybucket/data/images/img-bbb.png",
        ],
    })

    def test_image_gen_minimal(self, mock_get_connection, mocker):
        """image-gen with volume output returns oss_path and volume_path."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "生成一只猫", "-o", "volume://test_vol/images"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["images"]) == 1
        img = output["data"]["images"][0]
        assert img["oss_path"] == "oss://mybucket/data/images/c58b7714-b147.png"
        assert img["volume_path"] == "volume://test_vol/images/c58b7714-b147.png"
        assert output["data"]["usage"] == {"height": 720, "image_count": 1, "width": 1280}
        assert "model" not in output["data"]
        # Verify SQL: no model -> ai_gen(json, to_file(...))
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s, to_file(%s, %s, %s))"
        request = json.loads(call_args[0][1][0])
        assert request["prompt"] == "生成一只猫"
        assert request["output_dir"] == "oss://mybucket/data/images"
        assert call_args[0][1][1] == "oss://mybucket/data/"
        assert call_args[0][1][2] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert call_args[0][1][3] == "acs:ram::123456:role/AliyunHologresDefaultRole"
        mock_get_connection.close.assert_called_once()

    def test_image_gen_with_model(self, mock_get_connection, mocker):
        """image-gen with --model uses ai_gen(model, json, to_file(...))."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-m", "qwen-image-2.0", "-o", "volume://test_vol/images",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["model"] == "qwen-image-2.0"
        assert len(output["data"]["images"]) == 1
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s, %s, to_file(%s, %s, %s))"
        assert call_args[0][1][0] == "qwen-image-2.0"

    def test_image_gen_multiple_images(self, mock_get_connection, mocker):
        """image-gen returns multiple images with oss_path and volume_path."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE_MULTI}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-n", "2", "-o", "volume://test_vol/images",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["data"]["images"]) == 2
        assert output["data"]["images"][0]["oss_path"].endswith("img-aaa.png")
        assert output["data"]["images"][1]["volume_path"] == "volume://test_vol/images/img-bbb.png"
        assert output["data"]["usage"]["image_count"] == 2

    def test_image_gen_no_sub_path(self, mock_get_connection, mocker):
        """image-gen with volume root only (no sub_path)."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["output_dir"] == "oss://mybucket/data/"

    def test_image_gen_with_all_options(self, mock_get_connection, mocker):
        """image-gen with all options builds complete JSON."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
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
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][1])
        assert request["prompt"] == "猫"
        assert request["negative_prompt"] == "低画质"
        assert request["output_dir"] == "oss://mybucket/data/output"
        assert request["parameters"]["size"] == "1280*720"
        assert request["parameters"]["n"] == 2
        assert request["parameters"]["prompt_extend"] is False
        assert request["parameters"]["watermark"] is True
        assert request["parameters"]["seed"] == 42

    def test_image_gen_partial_options(self, mock_get_connection, mocker):
        """image-gen with partial options only includes specified params."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "--size", "1280*720", "-n", "3",
            "-o", "volume://test_vol/out",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["prompt"] == "猫"
        assert request["parameters"]["size"] == "1280*720"
        assert request["parameters"]["n"] == 3
        assert "negative_prompt" not in request
        assert "prompt_extend" not in request["parameters"]

    def test_image_gen_negative_prompt_only(self, mock_get_connection, mocker):
        """negative_prompt is at top level, not inside parameters."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "--negative-prompt", "模糊", "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["negative_prompt"] == "模糊"
        # parameters should only contain output_dir-related fields (none here)
        assert "parameters" not in request

    def test_image_gen_table_format(self, mock_get_connection, mocker):
        """image-gen with table format outputs volume paths, one per line."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE_MULTI}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "-f", "table", "ai", "image-gen", "猫", "-o", "volume://test_vol/images",
        ])
        assert result.exit_code == 0
        assert "volume://test_vol/images/img-aaa.png" in result.output
        assert "volume://test_vol/images/img-bbb.png" in result.output

    def test_image_gen_json_parse_failure_fallback(self, mock_get_connection, mocker):
        """image-gen falls back to raw_result when response is not valid JSON."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": "not-json-response"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == "not-json-response"
        assert "images" not in output["data"]

    def test_image_gen_no_oss_paths_fallback(self, mock_get_connection, mocker):
        """image-gen falls back when JSON has no image_oss_paths field."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [
            {"ai_gen": '{"requestId": "abc", "other": 1}'}
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["raw_result"] == '{"requestId": "abc", "other": 1}'

    def test_image_gen_connection_error(self, mocker):
        """image-gen handles connection error gracefully."""
        _patch_load_config(mocker)
        from hologres_cli.connection import DSNError
        mocker.patch("hologres_cli.commands.ai.get_connection",
                     side_effect=DSNError("No profile configured"))
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_image_gen_query_error(self, mock_get_connection, mocker):
        """image-gen handles SQL execution error."""
        _patch_load_config(mocker)
        mock_get_connection.execute.side_effect = Exception("model not supported")
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_image_gen_empty_result(self, mock_get_connection, mocker):
        """image-gen handles empty result."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == ""

    def test_image_gen_null_result(self, mock_get_connection, mocker):
        """image-gen handles NULL return."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": None}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["raw_result"] == ""

    def test_image_gen_parameterized_query(self, mock_get_connection, mocker):
        """image-gen uses parameterized query to prevent SQL injection."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "'; DROP TABLE users; --", "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][0] == "SELECT ai_gen(%s, to_file(%s, %s, %s))"

    def test_image_gen_missing_prompt(self):
        """image-gen shows error when prompt is missing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "-o", "volume://test_vol"])
        assert result.exit_code != 0

    def test_image_gen_missing_output_dir(self):
        """image-gen shows error when --output-dir is missing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫"])
        assert result.exit_code != 0

    def test_image_gen_invalid_volume_uri(self, mock_get_connection, mocker):
        """image-gen returns INVALID_ARGS for non-volume:// URI."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "/tmp/images"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_image_gen_volume_not_found(self, mock_get_connection, mocker):
        """image-gen returns NOT_FOUND when volume does not exist."""
        _patch_load_config(mocker, {
            "current": "default",
            "profiles": [{"name": "default", "volumes": []}],
        })
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://nonexistent"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_image_gen_profile_no_volumes(self, mock_get_connection, mocker):
        """image-gen returns NOT_FOUND when profile has no volumes."""
        _patch_load_config(mocker, {
            "current": "default",
            "profiles": [{"name": "default"}],
        })
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_image_gen_prompt_extend_case_insensitive(self, mock_get_connection, mocker):
        """--prompt-extend accepts True/False case-insensitively."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "--prompt-extend", "True", "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["parameters"]["prompt_extend"] is True

    def test_image_gen_invalid_n_type(self):
        """-n with non-integer value should fail."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-n", "abc", "-o", "volume://test_vol",
        ])
        assert result.exit_code != 0

    def test_image_gen_output_dir_json_field(self, mock_get_connection, mocker):
        """output_dir is included in JSON request body with full OSS path."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-o", "volume://test_vol/my/sub",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["output_dir"] == "oss://mybucket/data/my/sub"

    def test_image_gen_to_file_uses_internal_endpoint(self, mock_get_connection, mocker):
        """to_file() uses internal endpoint from volume config."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        # to_file params: root, endpoint, rolearn
        params = call_args[0][1]
        assert params[1] == "oss://mybucket/data/"
        assert params[2] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert params[3] == "acs:ram::123456:role/AliyunHologresDefaultRole"
