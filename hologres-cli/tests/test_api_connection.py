"""Tests for api_connection module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hologres_cli.api_connection import (
    ApiConnectionError,
    HologresApiConnection,
    _ApiCursor,
    _ApiSessionShim,
    _build_masked_dsn,
    _create_client,
    _execute_statement_via_call_api,
    _quote_literal,
    _rows_from_response,
    _substitute_params,
    _validate_api_profile,
)


@pytest.fixture
def api_profile():
    """A complete profile suitable for API connection."""
    return {
        "name": "test-api",
        "region_id": "cn-hangzhou",
        "instance_id": "hgprecn-cn-test123",
        "nettype": "internet",
        "auth_mode": "ram",
        "access_key_id": "LTAI5tTestAK",
        "access_key_secret": "TestSK123",
        "database": "testdb",
        "port": 80,
        "connection_mode": "api",
    }


@pytest.fixture
def incomplete_profile():
    """A profile missing required API fields."""
    return {
        "name": "incomplete",
        "region_id": "cn-hangzhou",
        "database": "testdb",
    }


class TestValidateApiProfile:
    """Tests for _validate_api_profile."""

    def test_valid_profile(self, api_profile):
        # Should not raise
        _validate_api_profile(api_profile)

    def test_missing_access_key_id(self, api_profile):
        api_profile.pop("access_key_id")
        with pytest.raises(ApiConnectionError, match="access_key_id"):
            _validate_api_profile(api_profile)

    def test_missing_instance_id(self, api_profile):
        api_profile.pop("instance_id")
        with pytest.raises(ApiConnectionError, match="instance_id"):
            _validate_api_profile(api_profile)

    def test_missing_database(self, api_profile):
        api_profile.pop("database")
        with pytest.raises(ApiConnectionError, match="database"):
            _validate_api_profile(api_profile)

    def test_multiple_missing(self, incomplete_profile):
        with pytest.raises(ApiConnectionError, match="access_key_id.*instance_id"):
            _validate_api_profile(incomplete_profile)


class TestBuildMaskedDsn:
    """Tests for _build_masked_dsn."""

    def test_with_endpoint(self, api_profile):
        api_profile["endpoint"] = "custom-host.aliyuncs.com"
        dsn = _build_masked_dsn(api_profile)
        assert "hologres+api://" in dsn
        assert "***" in dsn
        assert "custom-host.aliyuncs.com" in dsn
        assert "testdb" in dsn

    def test_without_endpoint(self, api_profile):
        dsn = _build_masked_dsn(api_profile)
        assert "hologres+api://" in dsn
        assert "hgprecn-cn-test123-cn-hangzhou" in dsn
        assert "***" in dsn

    def test_with_endpoint_containing_port(self, api_profile):
        """endpoint 带 :80 时,masked DSN 不出现双端口（与 JDBC 路径一致）。"""
        api_profile["endpoint"] = "custom-host.aliyuncs.com:80"
        dsn = _build_masked_dsn(api_profile)
        assert ":80:80" not in dsn
        assert "@custom-host.aliyuncs.com:80/" in dsn


class TestQuoteLiteral:
    """Tests for _quote_literal."""

    def test_none(self):
        assert _quote_literal(None) == "NULL"

    def test_bool_true(self):
        assert _quote_literal(True) == "TRUE"

    def test_bool_false(self):
        assert _quote_literal(False) == "FALSE"

    def test_int(self):
        assert _quote_literal(42) == "42"

    def test_float(self):
        assert _quote_literal(3.14) == "3.14"

    def test_string(self):
        assert _quote_literal("hello") == "'hello'"

    def test_string_with_quotes(self):
        assert _quote_literal("it's") == "'it''s'"

    def test_bytes(self):
        assert _quote_literal(b"abc") == "'abc'"

    def test_unsupported_type(self):
        with pytest.raises(ApiConnectionError, match="Unsupported parameter type"):
            _quote_literal({"key": "value"})


class TestSubstituteParams:
    """Tests for _substitute_params."""

    def test_no_params(self):
        assert _substitute_params("SELECT 1", None) == "SELECT 1"

    def test_empty_params(self):
        assert _substitute_params("SELECT 1", ()) == "SELECT 1"

    def test_single_param(self):
        result = _substitute_params("SELECT * FROM t WHERE id = %s", (42,))
        assert result == "SELECT * FROM t WHERE id = 42"

    def test_multiple_params(self):
        result = _substitute_params(
            "SELECT * FROM t WHERE id = %s AND name = %s",
            (1, "Alice"),
        )
        assert result == "SELECT * FROM t WHERE id = 1 AND name = 'Alice'"

    def test_param_count_mismatch(self):
        with pytest.raises(ApiConnectionError, match="Parameter count mismatch"):
            _substitute_params("SELECT %s, %s", (1,))


class TestRowsFromResponse:
    """Tests for _rows_from_response."""

    def test_empty_body(self):
        assert _rows_from_response({}) == []

    def test_data_none(self):
        assert _rows_from_response({"data": None}) == []

    def test_data_bool(self):
        assert _rows_from_response({"data": True}) == []

    # ---- Documented API response structure ----

    def test_documented_structure_results_with_records(self):
        """The official ExecuteStatement response uses data.results[0].records / columnMetadata."""
        body = {
            "data": {
                "results": [{
                    "success": True,
                    "sql": "SELECT id, name FROM users LIMIT 2",
                    "count": 2,
                    "truncated": False,
                    "queryId": "abc-123",
                    "columnMetadata": [
                        {"name": "id", "type": "int4", "nullable": False},
                        {"name": "name", "type": "text", "nullable": True},
                    ],
                    "records": [
                        ["1", "Alice"],
                        ["2", "Bob"],
                    ],
                }]
            }
        }
        rows = _rows_from_response(body)
        assert rows == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

    def test_documented_structure_empty_records(self):
        body = {
            "data": {
                "results": [{
                    "success": True,
                    "columnMetadata": [{"name": "n", "type": "int4", "nullable": True}],
                    "records": [],
                    "count": 0,
                }]
            }
        }
        assert _rows_from_response(body) == []

    def test_documented_structure_single_column(self):
        body = {
            "data": {
                "results": [{
                    "success": True,
                    "columnMetadata": [{"name": "n", "type": "int4", "nullable": True}],
                    "records": [["42"]],
                    "count": 1,
                }]
            }
        }
        rows = _rows_from_response(body)
        assert rows == [{"n": "42"}]

    def test_documented_structure_null_values(self):
        """NULL values are serialised as the string '\\N' by the API."""
        body = {
            "data": {
                "results": [{
                    "success": True,
                    "columnMetadata": [
                        {"name": "id", "type": "int4", "nullable": False},
                        {"name": "name", "type": "text", "nullable": True},
                    ],
                    "records": [["1", "\\N"]],
                    "count": 1,
                }]
            }
        }
        rows = _rows_from_response(body)
        assert rows == [{"id": "1", "name": "\\N"}]

    def test_documented_structure_per_statement_error(self):
        """results[0].success=False should raise ApiConnectionError."""
        body = {
            "data": {
                "results": [{
                    "success": False,
                    "errorCode": "SQL_ERROR",
                    "errorMessage": 'relation "nonexistent" does not exist',
                    "columnMetadata": [],
                    "records": [],
                }]
            }
        }
        with pytest.raises(ApiConnectionError, match="does not exist"):
            _rows_from_response(body)

    # ---- Legacy / fallback structures ----

    def test_data_list_of_dicts(self):
        rows = _rows_from_response({"data": [{"id": 1}, {"id": 2}]})
        assert rows == [{"id": 1}, {"id": 2}]

    def test_data_list_of_scalars(self):
        rows = _rows_from_response({"data": [1, 2, 3]})
        assert rows == [{"value": 1}, {"value": 2}, {"value": 3}]

    def test_data_dict_with_columns_and_rows(self):
        body = {
            "data": {
                "columns": [{"name": "id"}, {"name": "name"}],
                "rows": [[1, "Alice"], [2, "Bob"]],
            }
        }
        rows = _rows_from_response(body)
        assert rows == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    def test_data_dict_with_capitalized_keys(self):
        body = {
            "data": {
                "Columns": [{"Name": "col1"}],
                "Rows": [["val"]],
            }
        }
        rows = _rows_from_response(body)
        assert rows == [{"col1": "val"}]

    def test_data_dict_rows_are_dicts(self):
        body = {"data": {"rows": [{"a": 1}, {"a": 2}]}}
        rows = _rows_from_response(body)
        assert rows == [{"a": 1}, {"a": 2}]


class TestApiCursor:
    """Tests for _ApiCursor."""

    def test_context_manager(self, api_profile):
        with patch(
            "hologres_cli.api_connection._create_client"
        ) as mock_client:
            conn = HologresApiConnection(api_profile)
            cursor = _ApiCursor(conn)
            with cursor as cur:
                assert cur is cursor

    def test_execute_stores_rows(self, api_profile):
        mock_response = {
            "body": {
                "success": True,
                "data": {
                    "results": [{
                        "success": True,
                        "columnMetadata": [{"name": "id", "type": "int4", "nullable": True}],
                        "records": [["1"]],
                        "count": 1,
                    }]
                },
            }
        }
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            return_value=mock_response,
        ), patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            cursor = _ApiCursor(conn)
            cursor.execute("SELECT 1 AS id")
            assert cursor.fetchall() == [{"id": "1"}]
            assert cursor.description == [("id",)]
            assert cursor.rowcount == 1


class TestApiSessionShim:
    """Tests for _ApiSessionShim."""

    def test_execute_buffers_guc(self, api_profile):
        conn = HologresApiConnection(api_profile)
        initial_count = len(conn._pending_session_sql)
        conn.conn.execute("SET foo = 'bar'")
        assert len(conn._pending_session_sql) == initial_count + 1
        assert "SET foo = 'bar'" in conn._pending_session_sql


class TestHologresApiConnection:
    """Tests for HologresApiConnection."""

    def test_init_sets_properties(self, api_profile):
        conn = HologresApiConnection(api_profile)
        assert conn.database == "testdb"
        assert "hologres+api://" in conn.masked_dsn
        assert conn.autocommit is True
        assert conn.read_only is True

    def test_init_validates_profile(self, incomplete_profile):
        with pytest.raises(ApiConnectionError):
            HologresApiConnection(incomplete_profile)

    def test_close(self, api_profile):
        conn = HologresApiConnection(api_profile)
        conn.close()
        with pytest.raises(ApiConnectionError, match="closed"):
            conn.execute("SELECT 1")

    def test_context_manager(self, api_profile):
        with HologresApiConnection(api_profile) as conn:
            assert conn.database == "testdb"
        assert conn._closed is True

    def test_execute_success(self, api_profile):
        mock_response = {
            "body": {
                "success": True,
                "data": {
                    "results": [{
                        "success": True,
                        "columnMetadata": [{"name": "n", "type": "int4", "nullable": True}],
                        "records": [["42"]],
                        "count": 1,
                    }]
                },
            }
        }
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            return_value=mock_response,
        ) as mock_api, patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            result = conn.execute("SELECT 42 AS n")
            assert result == [{"n": "42"}]
            # Verify session GUCs were prepended
            call_args = mock_api.call_args
            sql_sent = call_args.kwargs.get("statement") or call_args[1] if len(call_args) > 1 else call_args.kwargs.get("statement", "")
            # Check via kwargs
            if "statement" in (call_args.kwargs or {}):
                assert "hg_computing_resource" in call_args.kwargs["statement"]

    def test_execute_with_params(self, api_profile):
        mock_response = {"body": {"success": True, "data": None}}
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            return_value=mock_response,
        ) as mock_api, patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            conn.execute("SELECT * FROM t WHERE id = %s", (99,))
            # Verify %s was substituted
            call_args = mock_api.call_args
            statement = call_args.kwargs.get("statement", "")
            assert "99" in statement
            assert "%s" not in statement

    def test_execute_api_failure(self, api_profile):
        mock_response = {
            "body": {
                "success": False,
                "errorCode": "SQL_ERROR",
                "errorMessage": "syntax error",
            }
        }
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            return_value=mock_response,
        ), patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            with pytest.raises(ApiConnectionError, match="syntax error"):
                conn.execute("SELEC 1")

    def test_execute_sdk_exception(self, api_profile):
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            side_effect=Exception("network timeout"),
        ), patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            with pytest.raises(ApiConnectionError, match="network timeout"):
                conn.execute("SELECT 1")

    def test_read_only_guc_buffered(self, api_profile):
        conn = HologresApiConnection(api_profile, read_only=True)
        assert any("default_transaction_read_only" in s for s in conn._pending_session_sql)

    def test_not_read_only(self, api_profile):
        conn = HologresApiConnection(api_profile, read_only=False)
        assert not any("default_transaction_read_only" in s for s in conn._pending_session_sql)

    def test_cursor_interface(self, api_profile):
        mock_response = {
            "body": {
                "success": True,
                "data": {
                    "results": [{
                        "success": True,
                        "columnMetadata": [{"name": "x", "type": "int4", "nullable": True}],
                        "records": [["1"]],
                        "count": 1,
                    }]
                },
            }
        }
        with patch(
            "hologres_cli.api_connection._execute_statement_via_call_api",
            return_value=mock_response,
        ), patch("hologres_cli.api_connection._create_client"):
            conn = HologresApiConnection(api_profile)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS x")
                assert cur.fetchall() == [{"x": "1"}]
                assert cur.description == [("x",)]


class TestExecuteStatementRequestBody:
    """Verify that _execute_statement_via_call_api builds the request body
    with the correct field names per the official API schema.

    See: https://help.aliyun.com/zh/hologres/developer-reference/api-hologram-2022-06-01-executestatement
    """

    def _call_with_captured_body(self, mocker):
        """Helper: invoke _execute_statement_via_call_api and return the captured body dict."""
        import sys
        from hologres_cli import api_connection

        captured_body = {}

        class FakeOpenApiRequest:
            def __init__(self, **kwargs):
                captured_body.update(kwargs.get("body", {}))

        class FakeParams:
            def __init__(self, **kwargs):
                pass

        class FakeModels:
            Config = mocker.MagicMock()
            OpenApiRequest = FakeOpenApiRequest
            Params = FakeParams

        class FakeUtilModels:
            RuntimeOptions = mocker.MagicMock

        # Stub alibabacloud_openapi_util so the import inside the function succeeds.
        fake_util = mocker.MagicMock()
        fake_util.Client.get_encode_param = mocker.MagicMock(return_value="hgprecn-cn-test")
        mocker.patch.dict(sys.modules, {"alibabacloud_openapi_util": fake_util,
                                         "alibabacloud_openapi_util.client": fake_util.Client})

        mock_client = mocker.MagicMock()
        mock_client.call_api.return_value = {"body": {"success": True, "data": None}}

        mocker.patch.object(
            api_connection, "_import_sdk",
            return_value=(mocker.MagicMock(), FakeModels, FakeUtilModels),
        )

        api_connection._execute_statement_via_call_api(
            client=mock_client,
            instance_id="hgprecn-cn-test",
            statement="SELECT 1",
            database="mydb",
        )
        return captured_body

    def test_body_uses_sql_and_dbname(self, mocker):
        """Body must use camelCase keys 'sql' and 'dbName', not 'Statement'/'Database'."""
        captured_body = self._call_with_captured_body(mocker)

        # Correct keys per official API schema
        assert "sql" in captured_body, "Body must use 'sql' (not 'Statement')"
        assert "dbName" in captured_body, "Body must use 'dbName' (not 'Database')"
        assert captured_body["sql"] == "SELECT 1"
        assert captured_body["dbName"] == "mydb"

        # Wrong keys must NOT be present
        assert "Statement" not in captured_body
        assert "Database" not in captured_body

    def test_body_includes_maxrows_and_querytimeout(self, mocker):
        """Body should include maxRows (API max=1000) and queryTimeout (API max=30s)."""
        captured_body = self._call_with_captured_body(mocker)

        assert captured_body.get("maxRows") == 1000
        assert captured_body.get("queryTimeout") == 30


class TestCreateClientSts:
    """L2: _create_client 的 STS 分支用 credential 对象（ram 保持字段方式）。"""

    def test_sts_uses_credential_object(self, mocker):
        from hologres_cli import api_connection

        fake_cred_client = mocker.MagicMock(name="credential_client")
        mocker.patch.object(api_connection.credentials, "get_credential_client",
                            return_value=fake_cred_client)
        captured = {}

        class FakeConfig:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        class FakeModels:
            Config = FakeConfig

        mocker.patch.object(api_connection, "_import_sdk",
                            return_value=(mocker.MagicMock(), FakeModels, None))
        api_connection._create_client({"auth_mode": "sts", "region_id": "cn-hangzhou"})
        assert captured.get("credential") is fake_cred_client
        assert "access_key_id" not in captured

    def test_ram_uses_ak_sk_fields(self, mocker):
        from hologres_cli import api_connection

        captured = {}

        class FakeConfig:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        class FakeModels:
            Config = FakeConfig

        mocker.patch.object(api_connection, "_import_sdk",
                            return_value=(mocker.MagicMock(), FakeModels, None))
        api_connection._create_client({
            "auth_mode": "ram", "access_key_id": "AK", "access_key_secret": "SK",
            "region_id": "cn-hangzhou",
        })
        assert captured.get("access_key_id") == "AK"
        assert captured.get("access_key_secret") == "SK"
        assert "credential" not in captured


class TestValidateApiProfileSts:
    """L2: _validate_api_profile 的 STS 分支（不强制 AK/SK，改校验凭证源）。"""

    def test_sts_passes_without_ak(self, mocker):
        from hologres_cli import api_connection

        mocker.patch.object(api_connection.credentials, "sts_prerequisites_met",
                            return_value=True)
        prof = {"auth_mode": "sts", "instance_id": "i", "region_id": "r",
                "database": "d", "credentials_uri": "http://x"}
        _validate_api_profile(prof)  # 不抛

    def test_sts_missing_prereqs_raises(self, mocker):
        from hologres_cli import api_connection

        mocker.patch.object(api_connection.credentials, "sts_prerequisites_met",
                            return_value=False)
        prof = {"auth_mode": "sts", "instance_id": "i", "region_id": "r", "database": "d"}
        with pytest.raises(ApiConnectionError, match="sts 模式"):
            _validate_api_profile(prof)
