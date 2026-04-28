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
            cli, ["--profile", test_profile, "table",
                  "list", "--schema", "public"]
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
            cli, ["--profile", test_profile,
                  "--format", "table", "table", "list"]
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

        column_names = [col["column_name"]
                        for col in output["data"]["columns"]]
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
            cli, ["--profile", test_profile, "table",
                  "show", "nonexistent_table_xyz"]
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
            cli, ["--profile", test_profile, "table",
                  "dump", f"public.{test_table}"]
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
            cli, ["--profile", test_profile, "table",
                  "dump", "public.nonexistent_xyz"]
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
            cli, ["--profile", test_profile, "table",
                  "size", f"public.{test_table}"]
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
            cli, ["--profile", test_profile, "table",
                  "size", "public.nonexistent_xyz"]
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
            cli, ["--profile", test_profile, "table",
                  "properties", "nonexistent_table_xyz"]
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
                "-c", "order_id BIGINT NOT NULL, user_id INT, created_at TIMESTAMPTZ NOT NULL",
                "--primary-key", "order_id",
                "--orientation", "column",
                "--distribution-key", "order_id",
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

            props = {r["property_key"]: r["property_value"]
                     for r in output2["data"]["rows"]}
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


@pytest.mark.integration
class TestPartitionLifecycleLive:
    """Integration tests for logical partition lifecycle management (single partition column)."""

    def test_partition_list_empty(self, test_profile, unique_table_name):
        """New logical partition table should have no partitions."""
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
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True

            result2 = runner.invoke(cli, [
                "--profile", test_profile, "partition", "list",
                "--table", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            assert output2["data"]["count"] == 0
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_create_returns_notice(self, test_profile, unique_table_name):
        """partition create on logical table returns notice (no-op)."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
            ])

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "create",
                "--table", unique_table_name,
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert "notice" in output["data"]
            assert "automatically" in output["data"]["notice"]
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_list_after_insert(self, test_profile, unique_table_name, integration_conn):
        """Insert data should auto-create partitions visible in partition list."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
                "--distribution-key", "b",
            ])

            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, ds) VALUES "
                f"('x', 1, '2025-04-01'), ('y', 2, '2025-04-02')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "list",
                "--table", unique_table_name,
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["count"] >= 2
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_drop_dry_run(self, test_profile, unique_table_name, integration_conn):
        """partition drop without --confirm should be dry-run, data unchanged."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
            ])
            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, ds) VALUES ('x', 1, '2025-04-01')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "drop",
                "--table", unique_table_name,
                "--partition", "2025-04-01",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["dry_run"] is True
            assert "DELETE FROM" in output["data"]["sql"]

            rows = integration_conn.execute(
                f"SELECT count(*) as cnt FROM {unique_table_name}"
            )
            assert rows[0]["cnt"] == 1
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_drop_with_confirm_and_verify(self, test_profile, unique_table_name, integration_conn):
        """partition drop --confirm should delete data and remove partition."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, ds DATE NOT NULL",
                "--primary-key", "b,ds",
                "--partition-by", "ds",
                "--partition-mode", "logical",
                "--orientation", "column",
                "--distribution-key", "b",
            ])
            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, ds) VALUES "
                f"('x', 1, '2025-04-01'), ('y', 2, '2025-04-02')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "drop",
                "--table", unique_table_name,
                "--partition", "2025-04-01", "--confirm",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            rows = integration_conn.execute(
                f"SELECT count(*) as cnt FROM {unique_table_name}"
            )
            assert rows[0]["cnt"] == 1

            result2 = runner.invoke(cli, [
                "--profile", test_profile, "partition", "list",
                "--table", unique_table_name,
            ])
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            # Only the 2025-04-02 partition should remain
            assert output2["data"]["count"] == 1
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_lifecycle_with_expiration(self, test_profile, unique_table_name):
        """Create logical partition table with lifecycle options and verify properties."""
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
                "--partition-keep-hot-window", "15 day",
                "--partition-require-filter", "true",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True

            props = {r["property_key"]: r["property_value"]
                     for r in output2["data"]["rows"]}
            assert props.get("is_logical_partitioned_table") == "true"
            # Verify at least one partition lifecycle property exists
            has_expiration = any(
                k for k in props if "partition_expiration" in k
            )
            assert has_expiration
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])


@pytest.mark.integration
class TestMultiColumnPartitionLive:
    """Integration tests for two-column logical partition tables."""

    def test_create_two_column_partition_dry_run(self, test_profile):
        """Dry-run for two-column logical partition table."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "create",
            "-n", "public.dry_run_2col_part",
            "-c", "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL",
            "--partition-by", "yy, mm",
            "--partition-mode", "logical",
            "--orientation", "column",
            "--partition-require-filter", "true",
            "--dry-run",
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        sql = output["data"]["sql"]
        assert "LOGICAL PARTITION BY LIST (yy, mm)" in sql
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql

    def test_create_two_column_partition_table(self, test_profile, unique_table_name):
        """Create and verify a two-column logical partition table."""
        runner = CliRunner()
        try:
            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL",
                "--partition-by", "yy, mm",
                "--partition-mode", "logical",
                "--orientation", "column",
                "--partition-require-filter", "true",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify table exists
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True

            # Verify is logical partition table
            result3 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            output3 = json.loads(result3.output)
            props = {r["property_key"]: r["property_value"]
                     for r in output3["data"]["rows"]}
            assert props.get("is_logical_partitioned_table") == "true"
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_list_multi_column(self, test_profile, unique_table_name, integration_conn):
        """Insert data and verify partition list for two-column partition table."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL",
                "--partition-by", "yy, mm",
                "--partition-mode", "logical",
                "--orientation", "column",
            ])

            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, yy, mm) VALUES "
                f"('x', 1, '2025', '04'), ('y', 2, '2025', '05')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "list",
                "--table", unique_table_name,
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["count"] >= 2
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_drop_multi_column_dry_run(self, test_profile, unique_table_name, integration_conn):
        """Dry-run partition drop with two-column key=value format."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL",
                "--partition-by", "yy, mm",
                "--partition-mode", "logical",
                "--orientation", "column",
            ])

            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, yy, mm) VALUES ('x', 1, '2025', '04')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "drop",
                "--table", unique_table_name,
                "--partition", "yy=2025,mm=04",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["dry_run"] is True
            assert "yy = '2025'" in output["data"]["sql"]
            assert "mm = '04'" in output["data"]["sql"]

            # Data should still exist
            rows = integration_conn.execute(
                f"SELECT count(*) as cnt FROM {unique_table_name}"
            )
            assert rows[0]["cnt"] == 1
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])

    def test_partition_drop_multi_column_with_confirm(self, test_profile, unique_table_name, integration_conn):
        """Drop partition with two-column key=value format and verify deletion."""
        runner = CliRunner()
        try:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "create",
                "-n", f"public.{unique_table_name}",
                "-c", "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL",
                "--partition-by", "yy, mm",
                "--partition-mode", "logical",
                "--orientation", "column",
            ])

            integration_conn.execute(
                f"INSERT INTO {unique_table_name} (a, b, yy, mm) VALUES "
                f"('x', 1, '2025', '04'), ('y', 2, '2025', '05')"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "partition", "drop",
                "--table", unique_table_name,
                "--partition", "yy=2025,mm=04", "--confirm",
            ])
            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify only one record remains
            rows = integration_conn.execute(
                f"SELECT count(*) as cnt FROM {unique_table_name}"
            )
            assert rows[0]["cnt"] == 1
        finally:
            runner.invoke(cli, [
                "--profile", test_profile, "table", "drop",
                unique_table_name, "--confirm",
            ])


@pytest.mark.integration
class TestTableAlterLive:
    """Integration tests for table alter command."""

    # --- dry-run ---

    def test_alter_dry_run(self, test_profile, test_table):
        """--dry-run should return SQL without executing, column not added."""
        runner = CliRunner()

        # Record columns before alter
        result_before = runner.invoke(cli, [
            "--profile", test_profile, "table", "show", test_table,
        ])
        output_before = json.loads(result_before.output)
        col_count_before = len(output_before["data"]["columns"])

        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "alter", test_table,
            "--add-column", "age INT", "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "ALTER TABLE" in output["data"]["sql"]
        assert "age" in output["data"]["sql"]

        # Column should NOT have been added
        result_after = runner.invoke(cli, [
            "--profile", test_profile, "table", "show", test_table,
        ])
        output_after = json.loads(result_after.output)
        col_names_after = [c["column_name"]
                           for c in output_after["data"]["columns"]]
        assert "age" not in col_names_after
        assert len(output_after["data"]["columns"]) == col_count_before

    # --- add-column ---

    def test_alter_add_single_column(self, test_profile, test_table):
        """Add a single column and verify via table show."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "alter", test_table,
            "--add-column", "age INT",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True

        # Verify column exists via table show
        result2 = runner.invoke(cli, [
            "--profile", test_profile, "table", "show", test_table,
        ])
        assert result2.exit_code == 0
        output2 = json.loads(result2.output)
        col_names = [c["column_name"] for c in output2["data"]["columns"]]
        assert "age" in col_names

    def test_alter_add_multiple_columns(self, test_profile, test_table):
        """Add multiple columns at once and verify all exist."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "alter", test_table,
            "--add-column", "col_a INT", "--add-column", "col_b TEXT",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True

        # Verify both columns exist
        result2 = runner.invoke(cli, [
            "--profile", test_profile, "table", "show", test_table,
        ])
        assert result2.exit_code == 0
        output2 = json.loads(result2.output)
        col_names = [c["column_name"] for c in output2["data"]["columns"]]
        assert "col_a" in col_names
        assert "col_b" in col_names

    # --- rename-column ---

    def test_alter_rename_column(self, test_profile, unique_table_name, integration_conn):
        """Rename a column and verify old name gone, new name present."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, name TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--rename-column", "name:full_name",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify via table show
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            col_names = [c["column_name"] for c in output2["data"]["columns"]]
            assert "name" not in col_names
            assert "full_name" in col_names
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")

    # --- ttl ---

    def test_alter_ttl(self, test_profile, unique_table_name, integration_conn):
        """Set TTL and verify via table properties."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--ttl", "864000",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            print(output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify via table properties
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            props = {r["property_key"]: r["property_value"]
                     for r in output2["data"]["rows"]}
            assert props.get("time_to_live_in_seconds") == "864000"
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")

    # --- dictionary-encoding-columns ---

    def test_alter_dictionary_encoding_columns(self, test_profile, unique_table_name, integration_conn):
        """Set dictionary encoding columns and verify via table properties."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--dictionary-encoding-columns", "val:on",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify via table properties
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            props = {r["property_key"]: r["property_value"]
                     for r in output2["data"]["rows"]}
            assert "val" in props.get("dictionary_encoding_columns", "")
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")

    # --- bitmap-columns ---

    def test_alter_bitmap_columns(self, test_profile, unique_table_name, integration_conn):
        """Set bitmap columns and verify via table properties."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--bitmap-columns", "val:on",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify via table properties
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True
            props = {r["property_key"]: r["property_value"]
                     for r in output2["data"]["rows"]}
            assert "val" in props.get("bitmap_columns", "")
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")

    # --- owner (dry-run only, actual execution depends on available users) ---

    def test_alter_owner_dry_run(self, test_profile, test_table):
        """Owner change dry-run should generate SQL with OWNER TO."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "alter", test_table,
            "--owner", "some_user", "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "OWNER TO" in output["data"]["sql"]

    # --- rename ---

    def test_alter_rename_table(self, test_profile, unique_table_name, integration_conn):
        """Rename table and verify old name gone, new name exists."""
        runner = CliRunner()
        new_name = f"{unique_table_name}_renamed"
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--rename", new_name,
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify new table exists via table show
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", new_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            assert output2["ok"] is True

            # Old name should not be found
            result3 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            output3 = json.loads(result3.output)
            assert output3["ok"] is False
        finally:
            # Clean up both names since rename may or may not have succeeded
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")
            integration_conn.execute(f"DROP TABLE IF EXISTS {new_name}")

    # --- no changes ---

    def test_alter_no_changes(self, test_profile, test_table):
        """No options specified should return NO_CHANGES error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", test_profile, "table", "alter", test_table,
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NO_CHANGES"

    # --- combination (transaction) ---

    def test_alter_multiple_options_transaction(self, test_profile, unique_table_name, integration_conn):
        """Multiple options wrapped in transaction, all should take effect."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter", unique_table_name,
                "--add-column", "age INT", "--ttl", "864000",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            print(output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify SQL contains transaction wrapping
            sql = output["data"]["sql"]
            assert "BEGIN;" in sql
            assert "COMMIT;" in sql

            # Verify column added via table show
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            col_names = [c["column_name"] for c in output2["data"]["columns"]]
            assert "age" in col_names

            # Verify TTL via table properties
            result3 = runner.invoke(cli, [
                "--profile", test_profile, "table", "properties", unique_table_name,
            ])
            assert result3.exit_code == 0
            output3 = json.loads(result3.output)
            props = {r["property_key"]: r["property_value"]
                     for r in output3["data"]["rows"]}
            assert props.get("time_to_live_in_seconds") == "864000"
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")

    # --- schema.table format ---

    def test_alter_with_schema_prefix(self, test_profile, unique_table_name, integration_conn):
        """Alter using public.table_name format should work correctly."""
        runner = CliRunner()
        try:
            integration_conn.execute(
                f"CREATE TABLE {unique_table_name} (id INT PRIMARY KEY, val TEXT)"
            )

            result = runner.invoke(cli, [
                "--profile", test_profile, "table", "alter",
                f"public.{unique_table_name}",
                "--add-column", "x INT",
            ])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["ok"] is True
            assert output["data"]["executed"] is True

            # Verify column added
            result2 = runner.invoke(cli, [
                "--profile", test_profile, "table", "show", unique_table_name,
            ])
            assert result2.exit_code == 0
            output2 = json.loads(result2.output)
            col_names = [c["column_name"] for c in output2["data"]["columns"]]
            assert "x" in col_names
        finally:
            integration_conn.execute(
                f"DROP TABLE IF EXISTS {unique_table_name}")
