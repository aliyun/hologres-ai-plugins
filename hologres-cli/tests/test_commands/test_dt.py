"""Tests for Dynamic Table (dt) command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli
from hologres_cli.commands.dt import _build_create_sql, _parse_table_name


# =========================================================================
# Unit tests for pure helper functions
# =========================================================================

class TestBuildCreateSql:
    """Tests for _build_create_sql function."""

    def _call(self, **overrides):
        """Helper to call _build_create_sql with defaults."""
        defaults = dict(
            table="my_dt", query="SELECT 1", freshness="10 minutes",
            refresh_mode=None, auto_refresh=None, cdc_format=None,
            computing_resource=None, serverless_cores=None,
            logical_partition_key=None, partition_active_time=None,
            partition_time_format=None, orientation=None,
            table_group=None, distribution_key=None,
            clustering_key=None, event_time_column=None,
            bitmap_columns=None, dictionary_encoding_columns=None,
            ttl=None, storage_mode=None, columns=None, refresh_gucs=(),
        )
        defaults.update(overrides)
        return _build_create_sql(**defaults)

    def test_minimal_create(self):
        sql = self._call(table="public.my_dt",
                         query="SELECT col1, SUM(col2) FROM src GROUP BY col1")
        assert "CREATE DYNAMIC TABLE public.my_dt" in sql
        assert "freshness = '10 minutes'" in sql
        assert "AS" in sql
        assert "SELECT col1" in sql

    def test_refresh_mode(self):
        sql = self._call(refresh_mode="incremental")
        assert "auto_refresh_mode = 'incremental'" in sql

    def test_auto_refresh_disabled(self):
        sql = self._call(auto_refresh=False)
        assert "auto_refresh_enable = false" in sql

    def test_auto_refresh_enabled(self):
        sql = self._call(auto_refresh=True)
        assert "auto_refresh_enable = true" in sql

    def test_cdc_format_binlog(self):
        sql = self._call(cdc_format="binlog")
        assert "base_table_cdc_format = 'binlog'" in sql

    def test_computing_resource_and_cores(self):
        sql = self._call(computing_resource="serverless", serverless_cores=32)
        assert "computing_resource = 'serverless'" in sql
        assert "refresh_guc_hg_experimental_serverless_computing_required_cores = '32'" in sql

    def test_logical_partition(self):
        sql = self._call(
            logical_partition_key="ds",
            partition_active_time="2 days",
            partition_time_format="YYYY-MM-DD",
        )
        assert "LOGICAL PARTITION BY LIST(ds)" in sql
        assert "auto_refresh_partition_active_time = '2 days'" in sql
        assert "partition_key_time_format = 'YYYY-MM-DD'" in sql

    def test_table_properties(self):
        sql = self._call(
            orientation="column", table_group="my_tg",
            distribution_key="user_id", clustering_key="created_at:asc",
            event_time_column="created_at",
            bitmap_columns="status,category",
            dictionary_encoding_columns="country,gender",
            ttl=2592000, storage_mode="hot",
        )
        assert "orientation = 'column'" in sql
        assert "table_group = 'my_tg'" in sql
        assert "distribution_key = 'user_id'" in sql
        assert "clustering_key = 'created_at:asc'" in sql
        assert "event_time_column = 'created_at'" in sql
        assert "bitmap_columns = 'status,category'" in sql
        assert "dictionary_encoding_columns = 'country,gender'" in sql
        assert "time_to_live_in_seconds = '2592000'" in sql
        assert "storage_mode = 'hot'" in sql

    def test_columns(self):
        sql = self._call(columns="col1,col2,col3")
        assert "CREATE DYNAMIC TABLE my_dt (col1,col2,col3)" in sql

    def test_refresh_gucs(self):
        sql = self._call(refresh_gucs=("timezone=GMT-8:00",
                                       "hg_experimental_enable_nullable_segment_key=true"))
        assert "refresh_guc_timezone = 'GMT-8:00'" in sql
        assert "refresh_guc_hg_experimental_enable_nullable_segment_key = 'true'" in sql

    def test_query_semicolon_stripped(self):
        sql = self._call(query="SELECT 1;")
        assert sql.endswith("SELECT 1")

    def test_full_real_world_example(self):
        sql = self._call(
            table="public.ads_dt_github_event",
            query="SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds",
            freshness="5 minutes", refresh_mode="auto", auto_refresh=True,
            cdc_format="stream", computing_resource="serverless", serverless_cores=32,
            logical_partition_key="ds", partition_active_time="2 days",
            partition_time_format="YYYY-MM-DD",
            orientation="column", distribution_key="repo_name",
        )
        assert "CREATE DYNAMIC TABLE public.ads_dt_github_event" in sql
        assert "LOGICAL PARTITION BY LIST(ds)" in sql
        assert "freshness = '5 minutes'" in sql
        assert "auto_refresh_enable = true" in sql
        assert "auto_refresh_mode = 'auto'" in sql
        assert "computing_resource = 'serverless'" in sql


class TestParseTableName:
    def test_with_schema(self):
        assert _parse_table_name("public.my_table") == ("public", "my_table")

    def test_without_schema(self):
        assert _parse_table_name("my_table") == ("public", "my_table")

    def test_custom_schema(self):
        assert _parse_table_name("test.my_dt") == ("test", "my_dt")


# =========================================================================
# CLI command tests
# =========================================================================

class TestDtCreateCmd:
    """Tests for dt create CLI command."""

    def test_create_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create",
            "--table", "my_dt", "--freshness", "10 minutes",
            "--query", "SELECT col1 FROM src", "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "CREATE DYNAMIC TABLE my_dt" in output["data"]["sql"]
        assert "freshness = '10 minutes'" in output["data"]["sql"]

    def test_create_dry_run_with_all_options(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create",
            "--table", "public.ads_report",
            "--freshness", "5 minutes",
            "--refresh-mode", "incremental",
            "--auto-refresh",
            "--cdc-format", "stream",
            "--computing-resource", "serverless",
            "--serverless-cores", "64",
            "--orientation", "column",
            "--distribution-key", "user_id",
            "--storage-mode", "hot",
            "--query", "SELECT user_id, COUNT(*) FROM orders GROUP BY user_id",
            "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        sql = output["data"]["sql"]
        assert "public.ads_report" in sql
        assert "auto_refresh_mode = 'incremental'" in sql
        assert "computing_resource = 'serverless'" in sql

    def test_create_executes_without_dry_run(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create",
            "--table", "my_dt", "--freshness", "10 minutes",
            "--query", "SELECT 1",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()

    def test_create_missing_table(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create", "--freshness", "10 minutes", "--query", "SELECT 1",
        ])
        assert result.exit_code != 0

    def test_create_missing_freshness(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create", "--table", "my_dt", "--query", "SELECT 1",
        ])
        assert result.exit_code != 0

    def test_create_missing_query(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create", "--table", "my_dt", "--freshness", "10 minutes",
        ])
        assert result.exit_code != 0

    def test_create_with_logical_partition_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create",
            "--table", "my_dt", "--freshness", "5 minutes",
            "--logical-partition-key", "ds",
            "--partition-active-time", "2 days",
            "--partition-time-format", "YYYY-MM-DD",
            "--query", "SELECT repo, cnt, ds FROM src GROUP BY repo, ds",
            "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "LOGICAL PARTITION BY LIST(ds)" in sql
        assert "auto_refresh_partition_active_time = '2 days'" in sql
        assert "partition_key_time_format = 'YYYY-MM-DD'" in sql

    def test_create_with_refresh_guc(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "create",
            "--table", "my_dt", "--freshness", "10 minutes",
            "--query", "SELECT 1",
            "--refresh-guc", "timezone=GMT-8:00",
            "--refresh-guc", "hg_experimental_enable_nullable_segment_key=true",
            "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "refresh_guc_timezone = 'GMT-8:00'" in sql


class TestDtListCmd:
    def test_list_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"schema_name": "public", "table_name": "my_dt",
             "refresh_mode": "incremental", "freshness": "10 minutes",
             "auto_refresh": "true", "computing_resource": "serverless"},
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "list"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 1
        assert output["data"]["rows"][0]["table_name"] == "my_dt"

    def test_list_empty(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "list"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True


class TestDtShowCmd:
    def test_show_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"property_key": "freshness", "property_value": "10 minutes"},
            {"property_key": "auto_refresh_mode", "property_value": "incremental"},
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "show", "public.my_dt"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2

    def test_show_not_found(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "show", "nonexistent"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_FOUND"

    def test_show_parses_schema(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"property_key": "freshness", "property_value": "10 minutes"},
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "show", "test_schema.my_dt"])
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][1] == ("test_schema", "my_dt")


class TestDtRefreshCmd:
    def test_refresh_basic(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "refresh", "my_dt"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "REFRESH DYNAMIC TABLE my_dt" in call_sql

    def test_refresh_overwrite_with_partition(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "refresh", "my_dt",
            "--overwrite", "--partition", "ds = '2025-04-01'", "--mode", "full",
        ])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "REFRESH OVERWRITE DYNAMIC TABLE my_dt" in call_sql
        assert "PARTITION (ds = '2025-04-01')" in call_sql
        assert "refresh_mode = 'full'" in call_sql

    def test_refresh_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "refresh", "my_dt", "--dry-run"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "REFRESH DYNAMIC TABLE my_dt" in output["data"]["sql"]


class TestDtAlterCmd:
    def test_alter_freshness(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "alter", "my_dt", "--freshness", "30 minutes"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "ALTER DYNAMIC TABLE my_dt SET" in call_sql
        assert "freshness = '30 minutes'" in call_sql

    def test_alter_disable_auto_refresh(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "alter", "my_dt", "--no-auto-refresh"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "auto_refresh_enable = false" in call_sql

    def test_alter_multiple_props(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "alter", "my_dt",
            "--freshness", "1 hours", "--refresh-mode", "full",
            "--computing-resource", "serverless",
        ])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "freshness = '1 hours'" in call_sql
        assert "auto_refresh_mode = 'full'" in call_sql
        assert "computing_resource = 'serverless'" in call_sql

    def test_alter_no_props_error(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "alter", "my_dt"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NO_CHANGES"

    def test_alter_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "dt", "alter", "my_dt", "--freshness", "30 minutes", "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["dry_run"] is True
        assert "ALTER DYNAMIC TABLE my_dt SET" in output["data"]["sql"]


class TestDtDropCmd:
    def test_drop_without_confirm_is_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "drop", "my_dt"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "DROP DYNAMIC TABLE my_dt" in output["data"]["sql"]

    def test_drop_with_confirm_executes(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "drop", "my_dt", "--confirm"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "DROP DYNAMIC TABLE my_dt" in call_sql

    def test_drop_with_if_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "drop", "my_dt", "--if-exists"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "DROP DYNAMIC TABLE IF EXISTS my_dt" in output["data"]["sql"]


class TestDtConvertCmd:
    def test_convert_single_table(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "convert", "my_old_dt"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "hg_dynamic_table_config_upgrade('my_old_dt')" in call_sql

    def test_convert_all_tables(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "convert", "--all"])
        assert result.exit_code == 0
        call_sql = mock_get_connection.execute.call_args[0][0]
        assert "hg_upgrade_all_normal_dynamic_tables()" in call_sql

    def test_convert_no_table_no_all_error(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "convert"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_convert_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "convert", "my_old_dt", "--dry-run"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["dry_run"] is True
        assert "hg_dynamic_table_config_upgrade" in output["data"]["sql"]

    def test_convert_all_dry_run(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "convert", "--all", "--dry-run"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["dry_run"] is True
        assert "hg_upgrade_all_normal_dynamic_tables" in output["data"]["sql"]


class TestDtCommandRegistered:
    """Test dt command group is properly registered."""

    def test_dt_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "refresh" in result.output
        assert "alter" in result.output
        assert "drop" in result.output
        assert "convert" in result.output
        assert "ddl" in result.output
        assert "lineage" in result.output
        assert "storage" in result.output
        assert "state-size" in result.output

    def test_dt_create_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "create", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--freshness" in result.output
        assert "--query" in result.output
        assert "--refresh-mode" in result.output
        assert "--dry-run" in result.output


# =========================================================================
# Tests for dt ddl
# =========================================================================

class TestDtDdlCmd:
    """Tests for dt ddl command."""

    def test_ddl_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE DYNAMIC TABLE public.my_dt ..."}
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "ddl", "public.my_dt"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "CREATE DYNAMIC TABLE" in data["data"]["ddl"]

    def test_ddl_not_found(self, mock_get_connection):
        mock_get_connection.execute.return_value = [{"hg_dump_script": None}]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "ddl", "public.no_such"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_ddl_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception("relation not found")
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "ddl", "public.bad"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False


# =========================================================================
# Tests for dt lineage
# =========================================================================

class TestDtLineageCmd:
    """Tests for dt lineage command."""

    def test_lineage_single_table(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"dynamic_table_namespace": "public", "dynamic_table_name": "my_dt",
             "table_namespace": "public", "table_name": "base_tbl",
             "dependency": "source", "base_table_type": "r"},
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "lineage", "public.my_dt"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]["rows"]) == 1

    def test_lineage_all(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"dynamic_table_namespace": "public", "dynamic_table_name": "dt1",
             "table_namespace": "public", "table_name": "src1",
             "dependency": "source", "base_table_type": "r"},
            {"dynamic_table_namespace": "public", "dynamic_table_name": "dt2",
             "table_namespace": "public", "table_name": "dt1",
             "dependency": "source", "base_table_type": "d"},
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "lineage", "--all"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]["rows"]) == 2

    def test_lineage_no_args_error(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "lineage"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["code"] == "INVALID_ARGS"

    def test_lineage_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception("no such table")
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "lineage", "public.my_dt"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False


# =========================================================================
# Tests for dt storage
# =========================================================================

class TestDtStorageCmd:
    """Tests for dt storage command."""

    def test_storage_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"table_name": "my_dt", "total_size": "1024 kB", "index_size": "256 kB"}
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "storage", "public.my_dt"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]["rows"]) == 1

    def test_storage_not_found(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "storage", "public.no_such"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_storage_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception("perm denied")
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "storage", "public.bad"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False


# =========================================================================
# Tests for dt state-size
# =========================================================================

class TestDtStateSizeCmd:
    """Tests for dt state-size command."""

    def test_state_size_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = [
            {"state_size": "512 kB"}
        ]
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "state-size", "public.my_dt"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["state_size"] == "512 kB"
        assert data["data"]["table"] == "public.my_dt"

    def test_state_size_empty(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "state-size", "public.no_such"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_state_size_query_error(self, mock_get_connection):
        mock_get_connection.execute.side_effect = Exception("function not found")
        runner = CliRunner()
        result = runner.invoke(cli, ["dt", "state-size", "public.bad"],
                               obj={"dsn": "hologres://u:p@h:1/db", "format": "json"})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is False
