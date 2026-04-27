"""Integration tests for table commands with real Hologres database."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestTableListLive:
    """Integration tests for table list command."""

    def test_list_tables(self, test_profile, test_table):
        """Test listing all tables, should include the test table."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "list"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] >= 1

        table_names = [r["table_name"] for r in output["data"]["rows"]]
        assert test_table in table_names

    def test_list_tables_with_schema_filter(self, test_profile, test_table):
        """Test listing tables with --schema public filter."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "list", "--schema", "public"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

        # All returned rows should be in public schema
        for row in output["data"]["rows"]:
            assert row["schema"] == "public"

    def test_list_tables_table_format(self, test_profile):
        """Test listing tables in table format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "--format", "table", "table", "list"]
        )

        assert result.exit_code == 0
        assert "table_name" in result.output.lower() or "schema" in result.output.lower()


@pytest.mark.integration
class TestTableShowLive:
    """Integration tests for table show command."""

    def test_show_table(self, test_profile, test_table):
        """Test showing table structure with columns and primary key."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "show", test_table]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "columns" in output["data"]
        assert "primary_key" in output["data"]
        assert len(output["data"]["columns"]) >= 1

        # test_table has id as primary key
        assert "id" in output["data"]["primary_key"]

    def test_show_table_columns_detail(self, test_profile, test_table):
        """Test that column details include required fields."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "show", test_table]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)

        column_names = [col["column_name"] for col in output["data"]["columns"]]
        assert "id" in column_names
        assert "name" in column_names

        # Verify each column has the expected fields
        for col in output["data"]["columns"]:
            assert "column_name" in col
            assert "data_type" in col
            assert "is_nullable" in col

    def test_show_nonexistent_table(self, test_profile):
        """Test showing a non-existent table returns TABLE_NOT_FOUND."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "show", "nonexistent_table_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"


@pytest.mark.integration
class TestTableDumpLive:
    """Integration tests for table dump command."""

    def test_dump_table(self, test_profile, test_table):
        """Test dumping table DDL via hg_dump_script."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "dump", f"public.{test_table}"]
        )

        # hg_dump_script may not be available in all Hologres versions
        if result.exit_code == 0:
            output = json.loads(result.output)
            if output["ok"]:
                assert "ddl" in output["data"]

    def test_dump_nonexistent_table(self, test_profile):
        """Test dumping a non-existent table."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "dump", "public.nonexistent_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False


@pytest.mark.integration
class TestTableSizeLive:
    """Integration tests for table size command."""

    def test_table_size(self, test_profile, test_table):
        """Test getting table storage size."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "size", f"public.{test_table}"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "size" in output["data"]
        assert "size_bytes" in output["data"]
        assert isinstance(output["data"]["size_bytes"], int)

    def test_table_size_nonexistent(self, test_profile):
        """Test getting size of a non-existent table."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "size", "public.nonexistent_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False


@pytest.mark.integration
class TestTablePropertiesLive:
    """Integration tests for table properties command."""

    def test_table_properties(self, test_profile, test_table):
        """Test showing table properties, should include orientation."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "properties", test_table]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] >= 1

        prop_keys = [r["property_key"] for r in output["data"]["rows"]]
        assert "orientation" in prop_keys

    def test_table_properties_nonexistent(self, test_profile):
        """Test properties of a non-existent table."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--profile", test_profile, "table", "properties", "nonexistent_table_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False


@pytest.mark.integration
class TestTableCreateLive:
    """Integration tests for table create command."""

    def test_create_table_dry_run(self, test_profile):
        """Test dry-run mode for regular table, no table created."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "create",
            "-n", "public.dry_run_test_table",
            "-c", "id BIGINT NOT NULL, name TEXT",
            "--primary-key", "id",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "CREATE TABLE" in output["data"]["sql"]
        assert "BEGIN;" in output["data"]["sql"]
        assert "COMMIT;" in output["data"]["sql"]

    def test_create_and_drop_table(self, test_profile, unique_table_name):
        """Test creating a regular table then cleaning up."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "id BIGINT NOT NULL, name TEXT",
                "--primary-key", "id",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify table exists via table show
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            assert "columns" in output2["data"]
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_create_table_with_properties(self, test_profile, unique_table_name):
        """Test creating a table with orientation, distribution_key, clustering_key."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "order_id BIGINT NOT NULL, user_id INT, created_at TIMESTAMPTZ",
                "--primary-key", "order_id",
                "--orientation", "column",
                "--distribution-key", "user_id",
                "--clustering-key", "created_at:asc",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify properties
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True

            props = {r["property_key"]: r["property_value"] for r in output2["data"]["rows"]}
            assert props.get("orientation") == "column"
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_create_table_if_not_exists(self, test_profile, unique_table_name):
        """Test --if-not-exists allows duplicate creation without error."""
        runner = CliRunner()
        try:
            # First create
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "id BIGINT NOT NULL, name TEXT",
                "--primary-key", "id",
                "--if-not-exists",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True

            # Second create with --if-not-exists should also succeed
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "id BIGINT NOT NULL, name TEXT",
                "--primary-key", "id",
                "--if-not-exists",
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_create_physical_partition_table_dry_run(self, test_profile):
        """Test dry-run for physical partition table with BEGIN/COMMIT + CALL set_table_property."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "create",
            "-n", "public.dry_run_phys_part",
            "-c", "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload TEXT",
            "--primary-key", "event_id,ds",
            "--partition-by", "ds",
            "--orientation", "column",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True

        sql = output["data"]["sql"]
        assert "BEGIN;" in sql
        assert "PARTITION BY LIST (ds)" in sql
        assert "CALL set_table_property" in sql
        assert "COMMIT;" in sql

    def test_create_physical_partition_table(self, test_profile, unique_table_name):
        """Test creating a physical partition table (PARTITION BY LIST)."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload TEXT",
                "--primary-key", "event_id,ds",
                "--partition-by", "ds",
                "--orientation", "column",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_create_logical_partition_table_dry_run(self, test_profile):
        """Test dry-run for logical partition table with LOGICAL PARTITION BY LIST + WITH(...)."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "create",
            "-n", "public.dry_run_logical_part",
            "-c", "a TEXT, b INT, ds DATE NOT NULL",
            "--primary-key", "b,ds",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--orientation", "column",
            "--distribution-key", "b",
            "--partition-expiration-time", "30 day",
            "--partition-require-filter", "true",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True

        sql = output["data"]["sql"]
        assert "LOGICAL PARTITION BY LIST (ds)" in sql
        assert "WITH" in sql
        assert "orientation" in sql
        assert "partition_expiration_time" in sql
        assert "partition_require_filter" in sql
        # Should NOT have BEGIN/COMMIT (logical uses WITH syntax)
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql

    def test_create_logical_partition_table(self, test_profile, unique_table_name):
        """Test creating a logical partition table (V3.1+)."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
                "--distribution-key", "b",
                "--partition-expiration-time", "30 day",
                "--partition-require-filter", "true",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_create_logical_partition_table_with_binlog(self, test_profile, unique_table_name):
        """Test creating a logical partition table with binlog options."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
                "--binlog", "replica",
                "--binlog-ttl", "86400",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])


@pytest.mark.integration
class TestTableDropLive:
    """Integration tests for table drop command."""

    def test_drop_dry_run(self, test_profile, test_table, integration_conn):
        """Test dry-run mode (no --confirm), table should still exist."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "drop", test_table,
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "DROP TABLE" in output["data"]["sql"]

        # Table should still exist
        rows = integration_conn.execute(
            f"SELECT count(*) as cnt FROM information_schema.tables "
            f"WHERE table_schema='public' AND table_name='{test_table}'"
        )
        assert rows[0]["cnt"] == 1

    def test_drop_with_confirm(self, test_profile, unique_table_name, integration_conn):
        """Test --confirm actually drops the table."""
        # Create table first
        integration_conn.execute(
            f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY)"
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "drop",
            unique_table_name, "--confirm",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True

        # Table should no longer exist
        rows = integration_conn.execute(
            f"SELECT count(*) as cnt FROM information_schema.tables "
            f"WHERE table_schema='public' AND table_name='{unique_table_name}'"
        )
        assert rows[0]["cnt"] == 0

    def test_drop_if_exists(self, test_profile):
        """Test --if-exists on a non-existent table does not error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "drop",
            "nonexistent_table_xyz", "--if-exists", "--confirm",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True


@pytest.mark.integration
class TestTableTruncateLive:
    """Integration tests for table truncate command."""

    def test_truncate_dry_run(self, test_profile, test_table_with_data, integration_conn):
        """Test dry-run mode, data should still exist."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "truncate", test_table_with_data,
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "TRUNCATE TABLE" in output["data"]["sql"]

        # Data should still be there
        rows = integration_conn.execute(
            f"SELECT count(*) as cnt FROM {test_table_with_data}"
        )
        assert rows[0]["cnt"] == 3

    def test_truncate_with_confirm(self, test_profile, test_table_with_data, integration_conn):
        """Test --confirm actually truncates the table data."""
        # Verify data exists first
        rows = integration_conn.execute(
            f"SELECT count(*) as cnt FROM {test_table_with_data}"
        )
        assert rows[0]["cnt"] == 3

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "truncate",
            test_table_with_data, "--confirm",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True

        # Data should be gone
        rows = integration_conn.execute(
            f"SELECT count(*) as cnt FROM {test_table_with_data}"
        )
        assert rows[0]["cnt"] == 0
