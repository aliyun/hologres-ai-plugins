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

    def test_list_search_matches_model_type(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_MODELS

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "list", "--search", "happy"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # MOCK_MODELS has one happyhorse-* row whose model_type contains "happy".
        assert output["data"]["count"] == 1
        assert output["data"]["rows"][0]["model_type"] == "happyhorse-1.0-t2v"

    def test_list_search_matches_model_name_only(self, mock_get_connection):
        # OR semantics: match when needle appears in model_name OR model_type.
        # Build rows where each branch is exercised independently so AND
        # semantics would silently drop one of them.
        disjoint = [
            # name contains "happy", type does NOT
            {"model_name": "happy_alias", "model_type": "qwen3-max",
             "model_provider": "bailian", "task": "chat/completions"},
            # type contains "happy", name does NOT
            {"model_name": "video_alias", "model_type": "happyhorse-1.0-i2v",
             "model_provider": "bailian", "task": "video-generation"},
            # neither
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
        # AND of exact --model-type and substring --search: hits one row.
        hit = runner.invoke(cli, [
            "model", "list",
            "--model-type", "happyhorse-1.0-t2v",
            "--search", "happy",
        ])
        assert json.loads(hit.output)["data"]["count"] == 1

        # AND with a model_type that has nothing in common: zero rows.
        miss = runner.invoke(cli, [
            "model", "list",
            "--model-type", "qwen3-vl-embedding",
            "--search", "happy",
        ])
        assert json.loads(miss.output)["data"]["count"] == 0


FAKE_CATALOG = {
    "qwen3-max": {
        "provider": "bailian",
        "task": "chat/completions",
        "model_url": "https://example/v1",
        "function_server_url": "http://example/proxy",
    },
    "qwen-image-2.0": {
        "provider": "bailian",
        "task": "image-generation",
        "model_url": "https://example/img",
        "function_server_url": "http://example/proxy",
    },
    "happyhorse-1.0-t2v": {
        "provider": "bailian",
        "task": "video-generation",
        "model_url": "https://example/video",
        "function_server_url": "http://example/proxy",
    },
}


class TestModelCatalogCmd:
    """Tests for model catalog command."""

    def test_catalog_returns_all(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 3
        row = output["data"]["rows"][0]
        assert set(row.keys()) == {"model_type", "model_provider", "task"}
        assert row["model_type"] == "qwen3-max"
        assert row["model_provider"] == "bailian"

    def test_catalog_filter_by_task(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog", "--task", "video-generation"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 1
        assert output["data"]["rows"][0]["model_type"] == "happyhorse-1.0-t2v"

    def test_catalog_filter_no_match(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog", "--task", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_catalog_table_format(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "model", "catalog"])

        assert result.exit_code == 0
        assert "model_type" in result.output
        assert "qwen3-max" in result.output
        assert "model_name" not in result.output

    def test_catalog_load_failure(self, mocker):
        mocker.patch(
            "hologres_cli.commands.model._load_catalog",
            side_effect=FileNotFoundError("models.json missing"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INTERNAL_ERROR"

    def test_catalog_does_not_open_db(self, mocker):
        # Catalog must not need a DB connection. If it does, get_connection
        # would be called and fail because DSN resolution is not mocked.
        spy = mocker.patch("hologres_cli.commands.model.get_connection")
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog"])

        assert result.exit_code == 0
        spy.assert_not_called()

    def test_catalog_search_substring(self, mocker):
        catalog = dict(FAKE_CATALOG)
        catalog["happyhorse-1.0-i2v"] = {
            "provider": "bailian",
            "task": "video-generation",
            "model_url": "https://example/video",
            "function_server_url": "http://example/proxy",
        }
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=catalog)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog", "--search", "happy"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 2
        types = {r["model_type"] for r in output["data"]["rows"]}
        assert types == {"happyhorse-1.0-t2v", "happyhorse-1.0-i2v"}

    def test_catalog_search_case_insensitive(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        upper = runner.invoke(cli, ["model", "catalog", "--search", "HAPPY"])
        lower = runner.invoke(cli, ["model", "catalog", "--search", "happy"])

        assert upper.exit_code == 0 and lower.exit_code == 0
        assert json.loads(upper.output) == json.loads(lower.output)
        assert json.loads(upper.output)["data"]["count"] == 1

    def test_catalog_search_no_match(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "catalog", "--search", "xyz_nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_catalog_search_combined_with_task(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "catalog",
            "--task", "video-generation",
            "--search", "happy",
        ])

        output = json.loads(result.output)
        assert output["data"]["count"] == 1
        assert output["data"]["rows"][0]["model_type"] == "happyhorse-1.0-t2v"

    def test_catalog_search_combined_yields_zero(self, mocker):
        mocker.patch("hologres_cli.commands.model._load_catalog", return_value=FAKE_CATALOG)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "catalog",
            "--task", "chat/completions",
            "--search", "happy",
        ])

        output = json.loads(result.output)
        assert output["data"]["count"] == 0

    def test_catalog_real_models_json_loadable(self):
        # Integration-ish: real bundled models.json must parse and contain
        # the expected per-entry fields. Guards against packaging regressions.
        from hologres_cli.commands.model import _load_catalog

        data = _load_catalog()
        assert isinstance(data, dict)
        assert len(data) > 0
        sample_key = next(iter(data))
        sample = data[sample_key]
        assert "provider" in sample
        assert "task" in sample


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
        # MR review: dry-run must not leak the underlying SQL.
        assert "sql" not in output["data"]
        # Dry-run must not touch the database.
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

    def test_delete_connection_error(self, mocker):
        mocker.patch(
            "hologres_cli.commands.model.get_connection",
            side_effect=DSNError("No DSN configured"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    @pytest.mark.parametrize("bad_name", [
        "name';DROP TABLE x;--",  # SQL injection attempt
        "with space",
        "semi;colon",
        "中文名",
        "name@host",
        "name/slash",
        "",  # explicit empty (when passed via Click)
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

    def test_delete_dry_run_does_not_connect(self, mocker):
        # Sentinel to ensure get_connection is never called in dry-run path.
        mock_get_conn = mocker.patch("hologres_cli.commands.model.get_connection")

        runner = CliRunner()
        result = runner.invoke(cli, ["model", "delete", "embed11"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        mock_get_conn.assert_not_called()


CREATE_CATALOG = {
    "qwen3-max": {
        "provider": "bailian",
        "task": "chat/completions",
        "model_url": "https://vpc-{region}.dashscope.aliyuncs.com/compatible-mode/v1",
        "function_server_url": "http://model-server-{region}.api.aliyun-inc.com:8000",
    },
    "wan2.2-kf2v-flash": {
        "provider": "bailian",
        "task": "video-generation",
        "model_url": "https://vpc-{region}.dashscope.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis",
        "function_server_url": "http://model-server-{region}.api.aliyun-inc.com:8000",
    },
    "kimi/kimi-k2.5": {
        "provider": "bailian",
        "task": "chat/completions",
        "model_url": "https://vpc-{region}.dashscope.aliyuncs.com/compatible-mode/v1",
        "function_server_url": "http://model-server-{region}.api.aliyun-inc.com:8000",
    },
}


def _patch_create_deps(mocker, region_id="cn-hangzhou", catalog=None):
    """Patch profile + catalog for `model create` tests."""
    mocker.patch(
        "hologres_cli.commands.model._load_catalog",
        return_value=catalog if catalog is not None else CREATE_CATALOG,
    )
    profile = {"name": "default", "region_id": region_id}
    mocker.patch("hologres_cli.commands.model.get_current_profile", return_value=profile)
    mocker.patch("hologres_cli.commands.model.get_profile", return_value=profile)


class TestModelCreateCmd:
    """Tests for model create command."""

    def test_create_success(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "my_chat",
            "--type", "qwen3-max",
            "--api-key", "sk-secret",
        ])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["model_name"] == "my_chat"
        assert out["data"]["model_type"] == "qwen3-max"
        assert out["data"]["created"] is True
        # MR review: per-skill we no longer expose provider/task/endpoint;
        # success response stays minimal.
        assert "endpoint" not in out["data"]
        assert "provider" not in out["data"]
        assert "task" not in out["data"]
        # The executed SQL still routes through psycopg.sql.Literal — verify
        # the live SQL contains the expected literals + the endpoint.
        actual_sql = mock_get_connection.execute.call_args[0][0]
        assert "CALL add_external_model" in actual_sql
        assert "'my_chat'" in actual_sql
        assert "'qwen3-max'" in actual_sql
        assert "'sk-secret'" in actual_sql  # only logs/errors mask api_key
        # cn-hangzhou triggers the '-prd' suffix on model_url host, but
        # function_server_url ('model-server-cn-hangzhou.api...') stays unchanged.
        assert (
            "http://model-server-cn-hangzhou.api.aliyun-inc.com:8000/providers/bailian"
            "?url=https://vpc-cn-hangzhou-prd.dashscope.aliyuncs.com/compatible-mode/v1"
        ) in actual_sql
        mock_get_connection.close.assert_called_once()

    def test_create_unknown_model_type(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)
        get_conn_spy = mocker.patch(
            "hologres_cli.commands.model.get_connection",
            wraps=lambda *a, **kw: mock_get_connection,
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "no-such-model",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "MODEL_TYPE_NOT_SUPPORTED"
        assert "hologres model catalog" in out["error"]["message"]
        get_conn_spy.assert_not_called()

    def test_create_missing_region_in_profile(self, mocker, mock_get_connection):
        # Profile without region_id triggers INVALID_ARGS; never connects.
        _patch_create_deps(mocker, region_id="")
        get_conn_spy = mocker.patch(
            "hologres_cli.commands.model.get_connection",
            wraps=lambda *a, **kw: mock_get_connection,
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_ARGS"
        assert "region_id" in out["error"]["message"]
        get_conn_spy.assert_not_called()

    def test_create_invalid_region_chars(self, mocker, mock_get_connection):
        _patch_create_deps(mocker, region_id="cn_hangzhou")  # underscore is illegal

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_ARGS"
        assert "invalid characters" in out["error"]["message"]

    def test_create_invalid_config_json(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)
        get_conn_spy = mocker.patch(
            "hologres_cli.commands.model.get_connection",
            wraps=lambda *a, **kw: mock_get_connection,
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
            "--config", "{notjson",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_INPUT"
        get_conn_spy.assert_not_called()

    def test_create_passes_config_as_string(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
            "--config", '{"timeout": 10}',
        ])

        assert result.exit_code == 0
        actual_sql = mock_get_connection.execute.call_args[0][0]
        # The 7th argument should be the JSON string literal, not expanded.
        assert "'{\"timeout\": 10}'" in actual_sql

    def test_create_dry_run_does_not_show_sql(self, mocker, mock_get_connection):
        # MR review: dry-run must NOT echo the underlying SQL or api_key.
        _patch_create_deps(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "my_chat",
            "--type", "qwen3-max",
            "--api-key", "sk-DRYSECRET",
            "--dry-run",
        ])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["dry_run"] is True
        assert out["data"]["model_name"] == "my_chat"
        assert out["data"]["model_type"] == "qwen3-max"
        # No SQL, no endpoint, no api_key anywhere.
        assert "sql" not in out["data"]
        assert "endpoint" not in out["data"]
        assert "sk-DRYSECRET" not in result.output
        mock_get_connection.execute.assert_not_called()

    def test_create_dry_run_does_not_connect(self, mocker):
        # Dry-run must not even open a connection.
        _patch_create_deps(mocker)
        get_conn_spy = mocker.patch("hologres_cli.commands.model.get_connection")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "my_chat",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
            "--dry-run",
        ])

        assert result.exit_code == 0
        get_conn_spy.assert_not_called()

    def test_create_query_error(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)
        mock_get_connection.execute.side_effect = Exception("duplicate key")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_create_connection_error(self, mocker):
        _patch_create_deps(mocker)
        mocker.patch(
            "hologres_cli.commands.model.get_connection",
            side_effect=DSNError("No DSN configured"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "CONNECTION_ERROR"

    def test_create_log_redacts_api_key(self, mocker, mock_get_connection):
        _patch_create_deps(mocker)
        log_spy = mocker.patch("hologres_cli.commands.model.log_operation")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-LEAK",
        ])

        assert result.exit_code == 0
        log_kwargs = log_spy.call_args.kwargs
        sql_str = log_kwargs.get("sql", "")
        assert "sk-LEAK" not in sql_str
        assert "'****'" in sql_str

    def test_create_alias_model_type(self, mocker, mock_get_connection):
        # Slash-prefixed aliases like 'kimi/kimi-k2.5' must round-trip without issue.
        _patch_create_deps(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "kimi_alias",
            "--type", "kimi/kimi-k2.5",
            "--api-key", "sk-x",
        ])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["model_type"] == "kimi/kimi-k2.5"
        # Verify the special path made it into the SQL endpoint.
        actual_sql = mock_get_connection.execute.call_args[0][0]
        assert "/providers/bailian?url=https://vpc-cn-hangzhou" in actual_sql

    def test_create_special_model_url_path(self, mocker, mock_get_connection):
        # wan2.2-kf2v-flash uses a non-standard model_url (image2video, not video-generation).
        # The endpoint is no longer in the JSON response, so verify via the executed SQL.
        _patch_create_deps(mocker)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "w22",
            "--type", "wan2.2-kf2v-flash",
            "--api-key", "sk-x",
        ])

        assert result.exit_code == 0
        actual_sql = mock_get_connection.execute.call_args[0][0]
        assert "image2video/video-synthesis" in actual_sql
        assert "video-generation/video-synthesis" not in actual_sql

    def test_create_catalog_load_failure(self, mocker, mock_get_connection):
        # Defensive: if models.json is missing/corrupt, fail with INTERNAL_ERROR
        # before even resolving the region.
        mocker.patch(
            "hologres_cli.commands.model._load_catalog",
            side_effect=FileNotFoundError("models.json missing"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "x",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INTERNAL_ERROR"

    def test_create_endpoint_prd_suffix_ap_southeast_1(self, mocker, mock_get_connection):
        # ap-southeast-1 must also trigger the '-prd' suffix on model_url host.
        _patch_create_deps(mocker, region_id="ap-southeast-1")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "sg_chat",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        assert result.exit_code == 0
        actual_sql = mock_get_connection.execute.call_args[0][0]
        assert "vpc-ap-southeast-1-prd.dashscope.aliyuncs.com" in actual_sql
        assert "vpc-ap-southeast-1.dashscope.aliyuncs.com" not in actual_sql
        # function_server_url stays without '-prd'.
        assert "model-server-ap-southeast-1.api.aliyun-inc.com:8000" in actual_sql

    def test_create_endpoint_no_prd_for_other_regions(self, mocker, mock_get_connection):
        # Non-whitelisted regions must keep the original model_url host.
        _patch_create_deps(mocker, region_id="cn-shanghai")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "model", "create",
            "--name", "sh_chat",
            "--type", "qwen3-max",
            "--api-key", "sk-x",
        ])

        assert result.exit_code == 0
        actual_sql = mock_get_connection.execute.call_args[0][0]
        assert "vpc-cn-shanghai.dashscope.aliyuncs.com" in actual_sql
        assert "vpc-cn-shanghai-prd" not in actual_sql
        assert "model-server-cn-shanghai.api.aliyun-inc.com:8000" in actual_sql
