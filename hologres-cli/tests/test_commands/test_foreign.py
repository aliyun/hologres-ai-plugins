"""Tests for foreign table command module."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.commands.foreign import (
    _build_foreign_alter_sql,
    _build_foreign_create_sql,
    _build_import_foreign_schema_sql,
)
from hologres_cli.main import cli


# ---------------------------------------------------------------------------
# Pure SQL-builder tests (no DB / no mocks needed)
# ---------------------------------------------------------------------------

class TestBuildForeignCreateSql:
    def test_two_layer_default_server(self):
        sql = _build_foreign_create_sql(
            schema_name="public",
            table_name="src_pt",
            columns="id text, pt text",
            server="odps_server",
            project_name="my_proj",
            odps_schema=None,
            odps_table_name="src_pt",
        )
        assert "CREATE FOREIGN TABLE public.src_pt" in sql
        assert "SERVER odps_server" in sql
        assert "project_name 'my_proj'" in sql
        assert "table_name 'src_pt'" in sql
        assert sql.rstrip().endswith(";")

    def test_three_layer_combines_project_and_schema(self):
        sql = _build_foreign_create_sql(
            schema_name="public",
            table_name="region",
            columns="r_regionkey bigint, r_name text",
            server="odps_server",
            project_name="odps_hologres",
            odps_schema="tpch_10g",
            odps_table_name="odps_region_10g",
        )
        assert "project_name 'odps_hologres#tpch_10g'" in sql
        assert "table_name 'odps_region_10g'" in sql

    def test_if_not_exists_clause(self):
        sql = _build_foreign_create_sql(
            schema_name="public", table_name="t", columns="id text",
            server="odps_server", project_name="p",
            odps_schema=None, odps_table_name=None, if_not_exists=True,
        )
        assert "CREATE FOREIGN TABLE IF NOT EXISTS public.t" in sql

    def test_default_odps_table_falls_back_to_local_name(self):
        sql = _build_foreign_create_sql(
            schema_name="public", table_name="t", columns="id text",
            server="odps_server", project_name="p",
            odps_schema=None, odps_table_name=None,
        )
        assert "table_name 't'" in sql

    def test_extra_options_are_appended(self):
        sql = _build_foreign_create_sql(
            schema_name="public", table_name="t", columns="id text",
            server="odps_server", project_name="p",
            odps_schema=None, odps_table_name=None,
            extra_options={"access_id": "abc"},
        )
        assert "access_id 'abc'" in sql

    def test_single_quote_in_value_is_escaped(self):
        sql = _build_foreign_create_sql(
            schema_name="public", table_name="t", columns="id text",
            server="odps_server", project_name="o'reilly",
            odps_schema=None, odps_table_name=None,
        )
        assert "project_name 'o''reilly'" in sql


class TestBuildForeignAlterSql:
    def test_no_changes_returns_empty(self):
        assert _build_foreign_alter_sql("public", "t") == ""

    def test_single_add_column(self):
        sql = _build_foreign_alter_sql(
            "public", "bank", add_columns=("score float8",),
        )
        assert sql == (
            "ALTER FOREIGN TABLE IF EXISTS public.bank ADD COLUMN score float8;"
        )

    def test_multiple_add_columns_in_one_statement(self):
        sql = _build_foreign_alter_sql(
            "public", "bank",
            add_columns=("a float8", "b float8"),
        )
        assert "ADD COLUMN a float8, ADD COLUMN b float8" in sql

    def test_drop_column(self):
        sql = _build_foreign_alter_sql(
            "public", "bank", drop_columns=("score",),
        )
        assert "DROP COLUMN score" in sql

    def test_rename_only(self):
        sql = _build_foreign_alter_sql(
            "public", "old", rename="new_name",
        )
        assert sql == (
            "ALTER FOREIGN TABLE IF EXISTS public.old RENAME TO new_name;"
        )

    def test_combined_changes_wrapped_in_transaction(self):
        sql = _build_foreign_alter_sql(
            "public", "bank",
            add_columns=("a float8",),
            drop_columns=("old_col",),
            rename="bank_v2",
        )
        assert sql.startswith("BEGIN;")
        assert "COMMIT;" in sql
        rename_pos = sql.rfind("RENAME TO bank_v2")
        drop_pos = sql.rfind("DROP COLUMN old_col")
        assert rename_pos > drop_pos > 0

    def test_no_if_exists_omits_clause(self):
        sql = _build_foreign_alter_sql(
            "public", "bank",
            drop_columns=("c",),
            if_exists=False,
        )
        assert "IF EXISTS" not in sql


class TestBuildImportForeignSchemaSql:
    def test_two_layer_with_limit_to(self):
        sql = _build_import_foreign_schema_sql(
            remote_schema="public_data",
            odps_schema=None,
            server="odps_server",
            into_schema="public",
            limit_to=("customer", "customer_address"),
            if_table_exist="update",
        )
        assert sql.startswith("IMPORT FOREIGN SCHEMA public_data")
        assert "LIMIT TO (customer, customer_address)" in sql
        assert "FROM SERVER odps_server" in sql
        assert "INTO public" in sql
        assert "if_table_exist 'update'" in sql

    def test_three_layer_quotes_remote_with_hash(self):
        sql = _build_import_foreign_schema_sql(
            remote_schema="odps_hologres",
            odps_schema="tpch_10g",
            server="odps_server",
            into_schema="public",
            limit_to=("odps_region_10g",),
            if_table_exist="error",
            if_unsupported_type="error",
        )
        assert '"odps_hologres#tpch_10g"' in sql
        assert "if_table_exist 'error'" in sql
        assert "if_unsupported_type 'error'" in sql

    def test_except_clause(self):
        sql = _build_import_foreign_schema_sql(
            remote_schema="db",
            odps_schema=None,
            server="odps_server",
            into_schema="public",
            exclude=("internal_t",),
        )
        assert "EXCEPT (internal_t)" in sql

    def test_limit_and_except_mutually_exclusive(self):
        with pytest.raises(ValueError):
            _build_import_foreign_schema_sql(
                remote_schema="db", odps_schema=None,
                server="odps_server", into_schema="public",
                limit_to=("a",), exclude=("b",),
            )

    def test_prefix_and_suffix(self):
        sql = _build_import_foreign_schema_sql(
            remote_schema="public_data",
            odps_schema=None,
            server="odps_server",
            into_schema="public",
            limit_to=("customer",),
            prefix="ext_", suffix="_v1",
        )
        assert "prefix 'ext_'" in sql
        assert "suffix '_v1'" in sql


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

MOCK_FOREIGN_ROWS = [
    {"schema": "public", "foreign_table": "src_pt",
     "server": "odps_server", "owner": "admin"},
    {"schema": "public", "foreign_table": "events",
     "server": "paimon_server", "owner": "admin"},
]


class TestForeignListCmd:
    def test_list_success(self, mock_get_connection):
        mock_get_connection.execute.return_value = MOCK_FOREIGN_ROWS
        result = CliRunner().invoke(cli, ["foreign", "list"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["count"] == 2

    def test_list_with_schema_and_server(self, mock_get_connection):
        mock_get_connection.execute.return_value = [MOCK_FOREIGN_ROWS[0]]
        result = CliRunner().invoke(
            cli, ["foreign", "list", "--schema", "public",
                  "--server", "odps_server"]
        )
        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "public" in str(call_args)
        assert "odps_server" in str(call_args)


class TestForeignShowCmd:
    def test_show_success(self, mock_get_connection):
        mock_get_connection.execute.side_effect = [
            [{
                "server": "odps_server",
                "options": ["project_name=my_proj", "table_name=src_pt"],
                "owner": "admin",
            }],
            [
                {"column_name": "id", "data_type": "text",
                 "is_nullable": "YES", "ordinal_position": 1},
                {"column_name": "pt", "data_type": "text",
                 "is_nullable": "YES", "ordinal_position": 2},
            ],
        ]
        result = CliRunner().invoke(cli, ["foreign", "show", "public.src_pt"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["server"] == "odps_server"
        assert out["data"]["options"]["project_name"] == "my_proj"
        assert len(out["data"]["columns"]) == 2

    def test_show_not_found(self, mock_get_connection):
        mock_get_connection.execute.return_value = []
        result = CliRunner().invoke(cli, ["foreign", "show", "public.missing"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "FOREIGN_TABLE_NOT_FOUND"

    def test_show_invalid_identifier(self, mock_get_connection):
        result = CliRunner().invoke(cli, ["foreign", "show", "bad name!"])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_INPUT"


class TestForeignCreateCmd:
    def test_create_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "create",
            "-n", "public.src_pt",
            "-c", "id text, pt text",
            "--project-name", "my_proj",
            "--odps-table", "src_pt",
            "--dry-run",
        ])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["dry_run"] is True
        assert "CREATE FOREIGN TABLE public.src_pt" in out["data"]["sql"]
        mock_get_connection.execute.assert_not_called()

    def test_create_three_layer_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "create",
            "-n", "public.region",
            "-c", "r_regionkey bigint, r_name text",
            "--project-name", "odps_hologres",
            "--odps-schema", "tpch_10g",
            "--odps-table", "odps_region_10g",
            "--dry-run",
        ])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert "project_name 'odps_hologres#tpch_10g'" in out["data"]["sql"]

    def test_create_executes(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "create",
            "-n", "public.t",
            "-c", "id text",
            "--project-name", "p",
        ])
        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()

    def test_create_invalid_extra_option(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "create",
            "-n", "public.t", "-c", "id text",
            "--project-name", "p",
            "--option", "bad-no-equals",
            "--dry-run",
        ])
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_ARGS"


class TestForeignAlterCmd:
    def test_alter_no_changes(self, mock_get_connection):
        result = CliRunner().invoke(cli, ["foreign", "alter", "public.bank"])
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "NO_CHANGES"

    def test_alter_add_column_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "alter", "public.bank",
            "--add-column", "score float8",
            "--dry-run",
        ])
        out = json.loads(result.output)
        assert out["ok"] is True
        assert "ADD COLUMN score float8" in out["data"]["sql"]

    def test_alter_rename_executes(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "alter", "public.old",
            "--rename", "new_name",
        ])
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()


class TestForeignDropCmd:
    def test_drop_default_is_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, ["foreign", "drop", "public.src_pt"])
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["dry_run"] is True
        assert "DROP FOREIGN TABLE public.src_pt" in out["data"]["sql"]
        mock_get_connection.execute.assert_not_called()

    def test_drop_with_confirm_executes(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "drop", "public.src_pt",
            "--if-exists", "--cascade", "--confirm",
        ])
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["executed"] is True
        sql = out["data"]["sql"]
        assert "IF EXISTS" in sql and "CASCADE" in sql

    def test_cascade_and_restrict_mutually_exclusive(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "drop", "public.src_pt",
            "--cascade", "--restrict",
        ])
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_ARGS"


class TestForeignImportCmd:
    def test_import_two_layer_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "import",
            "--remote-schema", "public_data",
            "--limit-to", "customer,customer_address",
            "--into", "public",
            "--if-table-exist", "update",
            "--dry-run",
        ])
        out = json.loads(result.output)
        assert out["ok"] is True
        sql = out["data"]["sql"]
        assert "IMPORT FOREIGN SCHEMA public_data" in sql
        assert "LIMIT TO (customer, customer_address)" in sql
        assert "if_table_exist 'update'" in sql

    def test_import_three_layer_dry_run(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "import",
            "--remote-schema", "odps_hologres",
            "--odps-schema", "tpch_10g",
            "--limit-to", "odps_region_10g",
            "--into", "public",
            "--if-table-exist", "error",
            "--if-unsupported-type", "error",
            "--dry-run",
        ])
        out = json.loads(result.output)
        sql = out["data"]["sql"]
        assert '"odps_hologres#tpch_10g"' in sql
        assert "if_unsupported_type 'error'" in sql

    def test_import_limit_and_except_mutually_exclusive(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "import",
            "--remote-schema", "db",
            "--into", "public",
            "--limit-to", "a",
            "--except", "b",
            "--dry-run",
        ])
        out = json.loads(result.output)
        assert out["ok"] is False
        assert out["error"]["code"] == "INVALID_ARGS"

    def test_import_executes(self, mock_get_connection):
        result = CliRunner().invoke(cli, [
            "foreign", "import",
            "--remote-schema", "public_data",
            "--limit-to", "customer",
            "--into", "public",
        ])
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()
