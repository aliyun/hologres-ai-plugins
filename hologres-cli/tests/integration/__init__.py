"""Integration tests for hologres-cli.

These tests require a real Hologres database connection.
Set TEST_PROFILE_NAME environment variable (preferred) or HOLOGRES_TEST_DSN (legacy).

Example:
    export TEST_PROFILE_NAME="default"
    # or legacy:
    export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"

Run with: pytest -m integration
"""
