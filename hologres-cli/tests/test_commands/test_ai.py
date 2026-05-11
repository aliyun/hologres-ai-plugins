"""Tests for AI commands."""

import copy
import json

import pytest
from click.testing import CliRunner

from hologres_cli.commands.ai import (
    _build_oss_output_dir,
    _build_video_params,
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
        # Verify SQL: no model -> ai_gen(json, to_file(...)) with rolearn inlined
        call_args = mock_get_connection.execute.call_args
        assert "to_file(%s, %s, 'acs:ram::123456:role/AliyunHologresDefaultRole')" in call_args[0][0]
        request = json.loads(call_args[0][1][0])
        assert request["prompt"] == "生成一只猫"
        assert request["output_dir"] == "oss://mybucket/data/images"
        assert call_args[0][1][1] == "oss://mybucket/data/"
        assert call_args[0][1][2] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert len(call_args[0][1]) == 3  # rolearn not in params
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
        assert call_args[0][0].startswith("SELECT ai_gen(%s, %s, to_file(%s, %s, '")
        assert call_args[0][1][0] == "qwen-image-2.0"
        assert len(call_args[0][1]) == 4  # model, json, root, endpoint

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
        # rolearn inlined, prompt still parameterized
        assert "to_file(%s, %s, '" in call_args[0][0]

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
        sql = call_args[0][0]
        # to_file params: root, endpoint as bind params; rolearn inlined in SQL
        params = call_args[0][1]
        assert params[1] == "oss://mybucket/data/"
        assert params[2] == "oss-cn-hangzhou-internal.aliyuncs.com"
        assert "acs:ram::123456:role/AliyunHologresDefaultRole" in sql

    def test_image_gen_rolearn_single_quote_escaped(self, mock_get_connection, mocker):
        """rolearn with single quote is escaped in SQL literal."""
        config = copy.deepcopy(SAMPLE_VOLUME_CONFIG)
        config["profiles"][0]["volumes"][0]["rolearn"] = "acs:ram::123:role/test'role"
        _patch_load_config(mocker, config)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "image-gen", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        sql = call_args[0][0]
        assert "test''role" in sql

    def test_image_gen_single_reference_url(self, mock_get_connection, mocker):
        """--reference-url resolves volume URI to OSS path in request body."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "参照风格", "-o", "volume://test_vol/output",
            "--reference-url", "volume://test_vol/images/ref.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["reference_urls"] == ["oss://mybucket/data/images/ref.png"]

    def test_image_gen_multiple_reference_urls(self, mock_get_connection, mocker):
        """Multiple --reference-url options produce an array."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "融合", "-o", "volume://test_vol/output",
            "--reference-url", "volume://test_vol/img1.png",
            "--reference-url", "volume://test_vol/img2.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["reference_urls"] == [
            "oss://mybucket/data/img1.png",
            "oss://mybucket/data/img2.png",
        ]

    def test_image_gen_reference_url_oss_passthrough(self, mock_get_connection, mocker):
        """oss:// reference URLs are passed through without resolution."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-o", "volume://test_vol",
            "--reference-url", "oss://other-bucket/ref.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["reference_urls"] == ["oss://other-bucket/ref.png"]

    def test_image_gen_reference_url_mixed(self, mock_get_connection, mocker):
        """Mixed volume:// and oss:// reference URLs."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "融合", "-o", "volume://test_vol/out",
            "--reference-url", "volume://test_vol/ref.png",
            "--reference-url", "oss://ext/other.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["reference_urls"] == [
            "oss://mybucket/data/ref.png",
            "oss://ext/other.png",
        ]

    def test_image_gen_reference_url_different_volume(self, mock_get_connection, mocker):
        """--reference-url can use a different volume than --output-dir."""
        config = copy.deepcopy(SAMPLE_VOLUME_CONFIG)
        config["profiles"][0]["volumes"].append({
            "name": "ref_vol",
            "type": "oss",
            "endpoint": "oss-cn-shanghai-internal.aliyuncs.com",
            "public_endpoint": "oss-cn-shanghai.aliyuncs.com",
            "root": "oss://refbucket/refs/",
            "rolearn": "acs:ram::789:role/RefRole",
            "access_key": "AK2",
            "access_secret": "SK2",
        })
        _patch_load_config(mocker, config)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "融合", "-o", "volume://test_vol/out",
            "--reference-url", "volume://ref_vol/person.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert request["reference_urls"] == ["oss://refbucket/refs/person.png"]

    def test_image_gen_no_reference_url(self, mock_get_connection, mocker):
        """No --reference-url means no reference_urls field in request."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        request = json.loads(call_args[0][1][0])
        assert "reference_urls" not in request

    def test_image_gen_reference_url_invalid_prefix(self, mocker):
        """--reference-url with invalid prefix returns INVALID_ARGS."""
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-o", "volume://test_vol",
            "--reference-url", "http://example.com/img.png",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_image_gen_reference_url_volume_not_found(self, mocker):
        """--reference-url referencing non-existent volume returns NOT_FOUND."""
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "猫", "-o", "volume://test_vol",
            "--reference-url", "volume://nonexistent/img.png",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"
        assert "nonexistent" in output["error"]["message"]

    def test_image_gen_reference_url_with_model(self, mock_get_connection, mocker):
        """--reference-url works correctly together with --model."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": self.MOCK_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "Q版人物", "-m", "wan2.7-image-pro",
            "-o", "volume://test_vol/output",
            "--reference-url", "volume://test_vol/ref.png",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][1][0] == "wan2.7-image-pro"
        request = json.loads(call_args[0][1][1])
        assert request["reference_urls"] == ["oss://mybucket/data/ref.png"]
        assert request["prompt"] == "Q版人物"


# ---------------------------------------------------------------------------
# Video generation tests — shared constants
# ---------------------------------------------------------------------------

MOCK_VIDEO_RESPONSE = json.dumps({
    "output": {
        "task_status": "SUCCEEDED",
        "task_id": "0385dc79-5ff8-4d82-bcb6-xxxxx",
        "video_url": "https://dashscope-result-sh.oss-cn-shanghai.aliyuncs.com/xxx.mp4",
        "video_oss_path": "oss://mybucket/data/output/generated.mp4",
    },
    "usage": {
        "duration": 5,
        "output_video_duration": 5,
        "video_count": 1,
        "SR": 720,
        "ratio": "16:9",
    },
    "request_id": "4909100c-7b5a-9f92-bfe5-xxxxx",
})

MOCK_VIDEO_FAILED_RESPONSE = json.dumps({
    "output": {
        "task_status": "FAILED",
        "code": "InvalidParameter",
        "message": "prompt is required",
    },
    "request_id": "xxxx",
})


@pytest.mark.unit
class TestBuildVideoParams:
    """Tests for _build_video_params helper."""

    def test_empty(self):
        assert _build_video_params() == {}

    def test_all_params(self):
        result = _build_video_params(
            resolution="720P", ratio="16:9", duration=10,
            watermark="true", seed=42, audio_setting="origin",
        )
        assert result == {
            "resolution": "720P", "ratio": "16:9", "duration": 10,
            "watermark": True, "seed": 42, "audio_setting": "origin",
        }

    def test_watermark_false(self):
        assert _build_video_params(watermark="false") == {"watermark": False}


@pytest.mark.unit
class TestAiT2vCmd:
    """Tests for 'hologres ai t2v' command."""

    def test_t2v_minimal(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "一只猫在跑", "-o", "volume://test_vol/output"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["video"]["oss_path"] == "oss://mybucket/data/output/generated.mp4"
        assert output["data"]["video"]["volume_path"] == "volume://test_vol/output/generated.mp4"
        assert output["data"]["model"] == "happyhorse-1.0-t2v"
        assert output["data"]["task_status"] == "SUCCEEDED"
        assert output["data"]["usage"]["duration"] == 5
        # Verify SQL structure
        call_args = mock_get_connection.execute.call_args
        sql = call_args[0][0]
        assert "ai_gen(%s, %s, to_file(%s, %s," in sql
        assert call_args[0][1][0] == "happyhorse-1.0-t2v"
        request = json.loads(call_args[0][1][1])
        assert request["prompt"] == "一只猫在跑"
        assert request["output_dir"] == "oss://mybucket/data/output"
        mock_get_connection.close.assert_called_once()

    def test_t2v_with_all_params(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "t2v", "猫", "-o", "volume://test_vol/out",
            "--resolution", "720P", "--ratio", "9:16",
            "--duration", "10", "--watermark", "false", "--seed", "42",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["parameters"]["resolution"] == "720P"
        assert request["parameters"]["ratio"] == "9:16"
        assert request["parameters"]["duration"] == 10
        assert request["parameters"]["watermark"] is False
        assert request["parameters"]["seed"] == 42

    def test_t2v_custom_model(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "t2v", "猫", "-m", "happyhorse-2.0-t2v", "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][1][0] == "happyhorse-2.0-t2v"
        output = json.loads(result.output)
        assert output["data"]["model"] == "happyhorse-2.0-t2v"

    def test_t2v_table_format(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "ai", "t2v", "猫", "-o", "volume://test_vol/output"])
        assert result.exit_code == 0
        assert "volume://test_vol/output/generated.mp4" in result.output

    def test_t2v_task_failed(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_FAILED_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert "QUERY_ERROR" == output["error"]["code"]
        assert "prompt is required" in output["error"]["message"]

    def test_t2v_json_parse_failure(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": "not-json"}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == "not-json"

    def test_t2v_missing_prompt(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "-o", "volume://test_vol"])
        assert result.exit_code != 0

    def test_t2v_missing_output_dir(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫"])
        assert result.exit_code != 0

    def test_t2v_connection_error(self, mocker):
        _patch_load_config(mocker)
        from hologres_cli.connection import DSNError
        mocker.patch("hologres_cli.commands.ai.get_connection",
                     side_effect=DSNError("No profile"))
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_t2v_query_error(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.side_effect = Exception("timeout")
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_t2v_volume_not_found(self, mock_get_connection, mocker):
        _patch_load_config(mocker, {
            "current": "default",
            "profiles": [{"name": "default", "volumes": []}],
        })
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://nonexistent"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_t2v_parameterized_query(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "'; DROP TABLE x; --", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "to_file(%s, %s, '" in call_args[0][0]

    def test_t2v_rolearn_escaped(self, mock_get_connection, mocker):
        config = copy.deepcopy(SAMPLE_VOLUME_CONFIG)
        config["profiles"][0]["volumes"][0]["rolearn"] = "role/test'role"
        _patch_load_config(mocker, config)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "test''role" in sql

    def test_t2v_empty_result(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["raw_result"] == ""

    def test_t2v_null_result(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": None}]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["data"]["raw_result"] == ""

    def test_t2v_no_video_oss_path(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [
            {"ai_gen": '{"output": {"task_status": "SUCCEEDED"}, "usage": {}}'}
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "volume://test_vol"])
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "raw_result" in output["data"]

    def test_t2v_invalid_volume_uri(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "t2v", "猫", "-o", "/tmp/output"])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"


@pytest.mark.unit
class TestAiI2vCmd:
    """Tests for 'hologres ai i2v' command."""

    def test_i2v_minimal(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫在跑", "--img-url", "volume://test_vol/frame.png",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["model"] == "happyhorse-1.0-i2v"
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["prompt"] == "猫在跑"
        assert request["img_url"] == "oss://mybucket/data/frame.png"

    def test_i2v_img_url_oss_passthrough(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫", "--img-url", "oss://other/frame.png",
            "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["img_url"] == "oss://other/frame.png"

    def test_i2v_with_params(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫", "--img-url", "oss://b/f.png",
            "-o", "volume://test_vol",
            "--resolution", "720P", "--duration", "8",
            "--watermark", "false", "--seed", "99",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["parameters"]["resolution"] == "720P"
        assert request["parameters"]["duration"] == 8
        assert request["parameters"]["watermark"] is False
        assert request["parameters"]["seed"] == 99

    def test_i2v_missing_img_url(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "i2v", "猫", "-o", "volume://test_vol"])
        assert result.exit_code != 0

    def test_i2v_img_url_volume_not_found(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫", "--img-url", "volume://nonexistent/f.png",
            "-o", "volume://test_vol",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_i2v_img_url_invalid_prefix(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫", "--img-url", "http://example.com/f.png",
            "-o", "volume://test_vol",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"


@pytest.mark.unit
class TestAiR2vCmd:
    """Tests for 'hologres ai r2v' command."""

    def test_r2v_minimal(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "女性在花园", "--reference-url", "volume://test_vol/girl.png",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["model"] == "happyhorse-1.0-r2v"
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["reference_urls"] == ["oss://mybucket/data/girl.png"]

    def test_r2v_multiple_refs(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "融合", "-o", "volume://test_vol/out",
            "--reference-url", "volume://test_vol/a.png",
            "--reference-url", "volume://test_vol/b.png",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["reference_urls"] == [
            "oss://mybucket/data/a.png",
            "oss://mybucket/data/b.png",
        ]

    def test_r2v_reference_url_mixed(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "融合", "-o", "volume://test_vol/out",
            "--reference-url", "volume://test_vol/a.png",
            "--reference-url", "oss://ext/b.png",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["reference_urls"] == [
            "oss://mybucket/data/a.png",
            "oss://ext/b.png",
        ]

    def test_r2v_with_all_params(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "猫", "-o", "volume://test_vol",
            "--reference-url", "oss://b/r.png",
            "--resolution", "1080P", "--ratio", "1:1",
            "--duration", "15", "--watermark", "true", "--seed", "7",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        p = request["parameters"]
        assert p["resolution"] == "1080P"
        assert p["ratio"] == "1:1"
        assert p["duration"] == 15
        assert p["watermark"] is True
        assert p["seed"] == 7

    def test_r2v_missing_reference_url(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ai", "r2v", "猫", "-o", "volume://test_vol"])
        assert result.exit_code != 0

    def test_r2v_ref_volume_not_found(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "猫", "-o", "volume://test_vol",
            "--reference-url", "volume://nonexistent/r.png",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_r2v_prompt_with_oss_url_unmodified(self, mock_get_connection, mocker):
        """prompt containing oss:// paths should not be modified."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        prompt_with_url = "人物oss://b/girl.png在跑步"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", prompt_with_url, "-o", "volume://test_vol",
            "--reference-url", "oss://b/girl.png",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["prompt"] == prompt_with_url


@pytest.mark.unit
class TestAiVideoEditCmd:
    """Tests for 'hologres ai video-edit' command."""

    def test_video_edit_minimal(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "转为动漫风格",
            "--video", "volume://test_vol/input.mp4",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["model"] == "happyhorse-1.0-video-edit"
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["prompt"] == "转为动漫风格"
        assert request["video"] == "oss://mybucket/data/input.mp4"

    def test_video_edit_with_refs(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "让人物骑马",
            "--video", "oss://b/train.mp4",
            "--reference-url", "volume://test_vol/char.png",
            "-o", "volume://test_vol/out",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["video"] == "oss://b/train.mp4"
        assert request["reference_urls"] == ["oss://mybucket/data/char.png"]

    def test_video_edit_video_oss_passthrough(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "编辑",
            "--video", "oss://other/v.mp4",
            "-o", "volume://test_vol",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["video"] == "oss://other/v.mp4"

    def test_video_edit_audio_setting(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "编辑",
            "--video", "oss://b/v.mp4", "-o", "volume://test_vol",
            "--audio-setting", "origin",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["parameters"]["audio_setting"] == "origin"

    def test_video_edit_with_all_params(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "编辑", "--video", "oss://b/v.mp4",
            "-o", "volume://test_vol",
            "--resolution", "720P", "--watermark", "false",
            "--seed", "123", "--audio-setting", "auto",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        p = request["parameters"]
        assert p["resolution"] == "720P"
        assert p["watermark"] is False
        assert p["seed"] == 123
        assert p["audio_setting"] == "auto"

    def test_video_edit_missing_video(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "编辑", "-o", "volume://test_vol",
        ])
        assert result.exit_code != 0

    def test_video_edit_video_volume_not_found(self, mock_get_connection, mocker):
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "编辑",
            "--video", "volume://nonexistent/v.mp4",
            "-o", "volume://test_vol",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"


@pytest.mark.unit
class TestUploadLocalFile:
    """Tests for local file upload support in AI commands."""

    def test_upload_local_file_success(self, mock_get_connection, mocker, tmp_path):
        """Local file is uploaded and OSS path is used in request."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        local_file = tmp_path / "frame.png"
        local_file.write_bytes(b"fake image data")

        mock_bucket = mocker.MagicMock()
        mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mock_bucket, "data/"),
        )
        mocker.patch("hologres_cli.commands.ai.uuid.uuid4",
                     return_value=mocker.MagicMock(hex="abcd1234deadbeef"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫在跑",
            "--img-url", str(local_file),
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        mock_bucket.put_object_from_file.assert_called_once_with(
            "data/_uploads/abcd1234_frame.png", str(local_file),
        )
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["img_url"] == "oss://mybucket/data/_uploads/abcd1234_frame.png"

    def test_upload_local_file_not_found(self, mock_get_connection, mocker):
        """Non-existent local file returns FILE_NOT_FOUND."""
        _patch_load_config(mocker)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫",
            "--img-url", "/nonexistent/path/file.png",
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "FILE_NOT_FOUND"

    def test_upload_volume_not_found(self, mock_get_connection, mocker, tmp_path):
        """Upload to non-existent volume returns NOT_FOUND."""
        _patch_load_config(mocker)
        local_file = tmp_path / "f.png"
        local_file.write_bytes(b"data")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫",
            "--img-url", str(local_file),
            "--upload-volume", "nonexistent_vol",
            "-o", "volume://test_vol/output",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_local_file_without_upload_volume(self, mock_get_connection, mocker, tmp_path):
        """Local file without --upload-volume returns INVALID_ARGS."""
        _patch_load_config(mocker)
        local_file = tmp_path / "f.png"
        local_file.write_bytes(b"data")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫",
            "--img-url", str(local_file),
            "-o", "volume://test_vol/output",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "--upload-volume" in output["error"]["message"]

    def test_upload_oss_error(self, mock_get_connection, mocker, tmp_path):
        """OSS upload failure returns OSS_ERROR."""
        _patch_load_config(mocker)
        local_file = tmp_path / "f.png"
        local_file.write_bytes(b"data")

        mock_bucket = mocker.MagicMock()
        mock_bucket.put_object_from_file.side_effect = Exception("network timeout")
        mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mock_bucket, "data/"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫",
            "--img-url", str(local_file),
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "OSS_ERROR"

    def test_r2v_mixed_local_and_remote(self, mock_get_connection, mocker, tmp_path):
        """r2v with mixed local file and oss:// reference URLs."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        local_file = tmp_path / "girl.png"
        local_file.write_bytes(b"data")

        mock_bucket = mocker.MagicMock()
        mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mock_bucket, "data/"),
        )
        mocker.patch("hologres_cli.commands.ai.uuid.uuid4",
                     return_value=mocker.MagicMock(hex="11112222deadbeef"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "r2v", "人物在跑步",
            "--reference-url", str(local_file),
            "--reference-url", "oss://bucket/fan.png",
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["reference_urls"][0] == "oss://mybucket/data/_uploads/11112222_girl.png"
        assert request["reference_urls"][1] == "oss://bucket/fan.png"

    def test_video_edit_local_video(self, mock_get_connection, mocker, tmp_path):
        """video-edit with local video file."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        local_file = tmp_path / "input.mp4"
        local_file.write_bytes(b"video data")

        mock_bucket = mocker.MagicMock()
        mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mock_bucket, "data/"),
        )
        mocker.patch("hologres_cli.commands.ai.uuid.uuid4",
                     return_value=mocker.MagicMock(hex="aabb1122deadbeef"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "video-edit", "转动漫",
            "--video", str(local_file),
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        request = json.loads(mock_get_connection.execute.call_args[0][1][1])
        assert request["video"] == "oss://mybucket/data/_uploads/aabb1122_input.mp4"

    def test_image_gen_local_reference(self, mock_get_connection, mocker, tmp_path):
        """image-gen with local reference file."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{
            "ai_gen": json.dumps({
                "image_oss_paths": ["oss://mybucket/data/output/img.png"],
                "usage": {"width": 1024, "height": 1024, "image_count": 1},
            })
        }]
        local_file = tmp_path / "ref.png"
        local_file.write_bytes(b"ref data")

        mock_bucket = mocker.MagicMock()
        mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mock_bucket, "data/"),
        )
        mocker.patch("hologres_cli.commands.ai.uuid.uuid4",
                     return_value=mocker.MagicMock(hex="ccdd3344deadbeef"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "image-gen", "生成Q版",
            "--reference-url", str(local_file),
            "--upload-volume", "test_vol",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # image-gen without --model: params = (request_json, root, endpoint)
        request = json.loads(mock_get_connection.execute.call_args[0][1][0])
        assert request["reference_urls"] == ["oss://mybucket/data/_uploads/ccdd3344_ref.png"]

    def test_net_intranet_passed_to_upload(self, mock_get_connection, mocker, tmp_path):
        """--net intranet is passed to _get_oss_client."""
        _patch_load_config(mocker)
        mock_get_connection.execute.return_value = [{"ai_gen": MOCK_VIDEO_RESPONSE}]
        local_file = tmp_path / "frame.png"
        local_file.write_bytes(b"data")

        mock_get_oss = mocker.patch(
            "hologres_cli.commands.ai._get_oss_client",
            return_value=(mocker.MagicMock(), "data/"),
        )
        mocker.patch("hologres_cli.commands.ai.uuid.uuid4",
                     return_value=mocker.MagicMock(hex="1234567890abcdef"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "ai", "i2v", "猫",
            "--img-url", str(local_file),
            "--upload-volume", "test_vol",
            "--net", "intranet",
            "-o", "volume://test_vol/output",
        ])
        assert result.exit_code == 0
        mock_get_oss.assert_called_once()
        assert mock_get_oss.call_args[0][1] == "intranet"
