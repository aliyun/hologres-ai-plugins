"""复杂 SQL 集成测试：查询 / DDL / DML / Dynamic Table，全程用 STS 三元组。

环境变量同 test_sts_real_instance.py（STS 三元组 + 实例信息）。用独立的
``sts_test_*`` 表并在 finally 清理，避免污染真实库。
"""

from __future__ import annotations

import os
import time

import pytest

from hologres_cli import connection, credentials
from hologres_cli.connection import get_connection

pytestmark = pytest.mark.integration

_STS_ENV = ["ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ALIBABA_CLOUD_SECURITY_TOKEN"]
_INSTANCE_ENV = ["HOLOGRES_TEST_REGION", "HOLOGRES_TEST_INSTANCE", "HOLOGRES_TEST_DATABASE"]


@pytest.fixture
def real_sts_profile():
    missing = [k for k in _STS_ENV + _INSTANCE_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"缺少环境变量: {missing}")
    return {
        "auth_mode": "sts",
        "region_id": os.environ["HOLOGRES_TEST_REGION"],
        "instance_id": os.environ["HOLOGRES_TEST_INSTANCE"],
        "database": os.environ["HOLOGRES_TEST_DATABASE"],
        "nettype": os.environ.get("HOLOGRES_TEST_NETTYPE", "internet"),
        "connection_mode": "jdbc",
        "credentials_uri": "",
    }


def _connect(real_sts_profile, mocker):
    mocker.patch.object(connection, "_resolve_profile_dict", return_value=dict(real_sts_profile))
    credentials.reset_credential_client_cache()
    return get_connection(read_only=False)  # 允许 DDL/DML


def test_query_ddl_dml(real_sts_profile, mocker):
    """查询(聚合) / CREATE TABLE / INSERT / UPDATE / DELETE 全流程。"""
    conn = _connect(real_sts_profile, mocker)
    try:
        conn.execute("DROP TABLE IF EXISTS sts_test_src")
        conn.execute("CREATE TABLE sts_test_src (id INT PRIMARY KEY, name TEXT, val INT)")
        conn.execute("INSERT INTO sts_test_src VALUES (1,'a',10),(2,'b',20),(3,'c',30)")

        rows = conn.execute("SELECT COUNT(*) AS c, SUM(val) AS s FROM sts_test_src")
        assert int(rows[0]["c"]) == 3
        assert int(rows[0]["s"]) == 60

        conn.execute("UPDATE sts_test_src SET name='A' WHERE id=1")
        assert conn.execute("SELECT name FROM sts_test_src WHERE id=1")[0]["name"] == "A"

        conn.execute("DELETE FROM sts_test_src WHERE id=3")
        assert int(conn.execute("SELECT COUNT(*) AS c FROM sts_test_src")[0]["c"]) == 2
    finally:
        try:
            conn.execute("DROP TABLE IF EXISTS sts_test_src")
        except Exception:
            pass
        conn.close()


def test_dynamic_table(real_sts_profile, mocker):
    """CREATE DYNAMIC TABLE (manual) + REFRESH + 查询（V3.1+ WITH 语法）。"""
    conn = _connect(real_sts_profile, mocker)
    try:
        conn.execute("DROP DYNAMIC TABLE IF EXISTS sts_test_dt")
        conn.execute("DROP TABLE IF EXISTS sts_test_src")
        conn.execute("CREATE TABLE sts_test_src (id INT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sts_test_src VALUES (1,'a'),(2,'b')")

        conn.execute(
            "CREATE DYNAMIC TABLE sts_test_dt "
            "WITH (freshness = '10 minutes', auto_refresh_mode = 'auto') "
            "AS SELECT id, name FROM sts_test_src"
        )
        conn.execute("REFRESH DYNAMIC TABLE sts_test_dt")
        time.sleep(2)  # 等首次刷新落盘

        rows = conn.execute("SELECT COUNT(*) AS c FROM sts_test_dt")
        assert int(rows[0]["c"]) >= 1
    finally:
        try:
            conn.execute("DROP DYNAMIC TABLE IF EXISTS sts_test_dt")
        except Exception:
            pass
        try:
            conn.execute("DROP TABLE IF EXISTS sts_test_src")
        except Exception:
            pass
        conn.close()
