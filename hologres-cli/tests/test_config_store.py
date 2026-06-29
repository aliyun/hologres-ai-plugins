"""Tests for config_store module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hologres_cli.config_store import (
    ConfigError,
    DEFAULT_PROFILE,
    ENDPOINT_TEMPLATES,
    SENSITIVE_KEYS,
    build_dsn_from_profile,
    delete_profile,
    get_current_profile,
    get_profile,
    list_profiles,
    load_config,
    mask_profile,
    migrate_from_legacy,
    save_config,
    set_profile,
    switch_profile,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_no_file(self, mock_home):
        """Test loading config when no file exists returns empty structure."""
        config = load_config()
        assert config["current"] == ""
        assert config["profiles"] == []
        assert config["meta_path"] == ""

    def test_load_config_valid(self, mock_config, sample_config):
        """Test loading valid config file."""
        config = load_config()
        assert config["current"] == sample_config["current"]
        assert len(config["profiles"]) == len(sample_config["profiles"])

    def test_load_config_invalid_json(self, mock_home):
        """Test loading invalid JSON raises ConfigError."""
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text("{invalid json}")

        with pytest.raises(ConfigError, match="Failed to read config file"):
            load_config()

    def test_load_config_missing_keys(self, mock_home):
        """Test loading config with missing keys adds defaults."""
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text("{}")

        config = load_config()
        assert config["current"] == ""
        assert config["profiles"] == []
        assert config["meta_path"] == ""


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config_creates_dir(self, mock_home):
        """Test save_config creates config directory."""
        config = {"current": "test", "profiles": [], "meta_path": ""}
        save_config(config)

        config_file = mock_home / ".hologres" / "config.json"
        assert config_file.exists()
        loaded = json.loads(config_file.read_text())
        assert loaded["current"] == "test"

    def test_save_config_overwrites(self, mock_config):
        """Test save_config overwrites existing file."""
        config = {"current": "new", "profiles": [], "meta_path": ""}
        save_config(config)

        config = load_config()
        assert config["current"] == "new"


class TestGetProfile:
    """Tests for get_profile function."""

    def test_get_profile_found(self, mock_config, sample_profile):
        """Test getting existing profile."""
        profile = get_profile("default")
        assert profile["name"] == "default"
        assert profile["region_id"] == sample_profile["region_id"]

    def test_get_profile_not_found(self, mock_config):
        """Test getting non-existent profile raises ConfigError."""
        with pytest.raises(ConfigError, match="Profile 'nonexistent' not found"):
            get_profile("nonexistent")

    def test_get_profile_no_config(self, mock_home):
        """Test getting profile when no config exists."""
        with pytest.raises(ConfigError, match="not found"):
            get_profile("default")


class TestGetCurrentProfile:
    """Tests for get_current_profile function."""

    def test_get_current_profile_success(self, mock_config, sample_profile):
        """Test getting current profile."""
        profile = get_current_profile()
        assert profile["name"] == "default"

    def test_get_current_profile_no_current(self, mock_home):
        """Test getting current profile when none set."""
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"current": "", "profiles": [], "meta_path": ""}))

        with pytest.raises(ConfigError, match="No current profile configured"):
            get_current_profile()

    def test_get_current_profile_no_config(self, mock_home):
        """Test getting current profile when no config file exists."""
        with pytest.raises(ConfigError, match="No current profile configured"):
            get_current_profile()


class TestSetProfile:
    """Tests for set_profile function."""

    def test_set_profile_create_new(self, mock_home):
        """Test creating a new profile."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "test"
        profile["database"] = "mydb"
        set_profile(profile)

        loaded = get_profile("test")
        assert loaded["database"] == "mydb"

    def test_set_profile_update_existing(self, mock_config, sample_profile):
        """Test updating an existing profile."""
        updated = dict(sample_profile)
        updated["database"] = "newdb"
        set_profile(updated)

        loaded = get_profile("default")
        assert loaded["database"] == "newdb"

    def test_set_profile_sets_current(self, mock_home):
        """Test first profile becomes current."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "first"
        set_profile(profile)

        config = load_config()
        assert config["current"] == "first"

    def test_set_profile_no_name(self, mock_home):
        """Test setting profile without name raises ConfigError."""
        with pytest.raises(ConfigError, match="must have a 'name' field"):
            set_profile({"database": "test"})

    def test_set_profile_preserves_current(self, mock_config):
        """Test adding new profile doesn't change current."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "second"
        set_profile(profile)

        config = load_config()
        assert config["current"] == "default"


class TestDeleteProfile:
    """Tests for delete_profile function."""

    def test_delete_profile_success(self, mock_config):
        """Test deleting an existing profile."""
        # Add a second profile first
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "second"
        set_profile(profile)

        delete_profile("second")
        with pytest.raises(ConfigError):
            get_profile("second")

    def test_delete_profile_not_found(self, mock_config):
        """Test deleting non-existent profile raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            delete_profile("nonexistent")

    def test_delete_current_profile_switches(self, mock_config):
        """Test deleting current profile switches to another."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "second"
        set_profile(profile)

        delete_profile("default")
        config = load_config()
        assert config["current"] == "second"

    def test_delete_last_profile(self, mock_config):
        """Test deleting the last profile clears current."""
        delete_profile("default")
        config = load_config()
        assert config["current"] == ""


class TestSwitchProfile:
    """Tests for switch_profile function."""

    def test_switch_profile_success(self, mock_config):
        """Test switching to existing profile."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "prod"
        set_profile(profile)

        switch_profile("prod")
        config = load_config()
        assert config["current"] == "prod"

    def test_switch_profile_not_found(self, mock_config):
        """Test switching to non-existent profile raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            switch_profile("nonexistent")


class TestListProfiles:
    """Tests for list_profiles function."""

    def test_list_profiles_empty(self, mock_home):
        """Test listing profiles when none exist."""
        profiles = list_profiles()
        assert profiles == []

    def test_list_profiles_with_current(self, mock_config):
        """Test listing profiles marks current."""
        profiles = list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "default"
        assert profiles[0]["current"] == "*"

    def test_list_profiles_multiple(self, mock_config):
        """Test listing multiple profiles."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "prod"
        profile["region_id"] = "cn-shanghai"
        set_profile(profile)

        profiles = list_profiles()
        assert len(profiles) == 2
        names = [p["name"] for p in profiles]
        assert "default" in names
        assert "prod" in names


class TestMaskProfile:
    """Tests for mask_profile function."""

    def test_mask_profile_hides_sensitive(self, sample_profile):
        """Test sensitive fields are masked."""
        masked = mask_profile(sample_profile)
        assert masked["access_key_secret"] != sample_profile["access_key_secret"]
        assert "***" in str(masked["access_key_secret"]) or masked["access_key_secret"].startswith("Tes")

    def test_mask_profile_preserves_non_sensitive(self, sample_profile):
        """Test non-sensitive fields are preserved."""
        masked = mask_profile(sample_profile)
        assert masked["name"] == sample_profile["name"]
        assert masked["region_id"] == sample_profile["region_id"]
        assert masked["database"] == sample_profile["database"]

    def test_mask_profile_empty_sensitive(self):
        """Test empty sensitive fields stay empty."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "test"
        profile["password"] = ""
        masked = mask_profile(profile)
        assert masked["password"] == ""

    def test_mask_profile_short_sensitive(self):
        """Test short sensitive values are fully masked."""
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "test"
        profile["password"] = "abc"
        masked = mask_profile(profile)
        assert masked["password"] == "***"


class TestBuildDsnFromProfile:
    """Tests for build_dsn_from_profile function."""

    def test_build_dsn_ram_with_endpoint(self):
        """Test DSN build with RAM auth and explicit endpoint."""
        profile = {
            "name": "test",
            "endpoint": "my-instance.hologres.aliyuncs.com",
            "auth_mode": "ram",
            "access_key_id": "LTAI5tTest",
            "access_key_secret": "SecretKey123",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert dsn.startswith("hologres://")
        assert "LTAI5tTest" in dsn
        assert "my-instance.hologres.aliyuncs.com" in dsn
        assert "mydb" in dsn

    def test_build_dsn_ram_auto_endpoint(self):
        """Test DSN build with auto-constructed endpoint."""
        profile = {
            "name": "test",
            "endpoint": "",
            "instance_id": "hgprecn-cn-abc123",
            "region_id": "cn-hangzhou",
            "nettype": "internet",
            "auth_mode": "ram",
            "access_key_id": "LTAI5tTest",
            "access_key_secret": "SecretKey123",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "hgprecn-cn-abc123-cn-hangzhou.hologres.aliyuncs.com" in dsn

    def test_build_dsn_basic_auth(self):
        """Test DSN build with basic auth."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "basic",
            "username": "myuser",
            "password": "mypass",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "myuser" in dsn
        assert "mypass" in dsn

    def test_build_dsn_no_instance_id(self):
        """Test error when no endpoint and no instance_id."""
        profile = {
            "name": "test",
            "endpoint": "",
            "instance_id": "",
            "region_id": "cn-hangzhou",
            "nettype": "internet",
            "auth_mode": "ram",
            "access_key_id": "test",
            "database": "mydb",
            "port": 80,
        }
        with pytest.raises(ConfigError, match="instance_id"):
            build_dsn_from_profile(profile)

    def test_build_dsn_no_database(self):
        """Test error when database not set."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "ram",
            "access_key_id": "test",
            "access_key_secret": "secret",
            "database": "",
            "port": 80,
        }
        with pytest.raises(ConfigError, match="database is required"):
            build_dsn_from_profile(profile)

    def test_build_dsn_no_access_key(self):
        """Test error when RAM auth without access_key_id."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "ram",
            "access_key_id": "",
            "database": "mydb",
            "port": 80,
        }
        with pytest.raises(ConfigError, match="access_key_id is required"):
            build_dsn_from_profile(profile)

    def test_build_dsn_unknown_auth_mode(self):
        """Test error with unknown auth_mode."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "unknown",
            "database": "mydb",
            "port": 80,
        }
        with pytest.raises(ConfigError, match="Unknown auth_mode"):
            build_dsn_from_profile(profile)

    def test_build_dsn_special_chars_encoded(self):
        """Test special characters in credentials are URL-encoded."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "basic",
            "username": "user@domain",
            "password": "p@ss/word",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "user%40domain" in dsn
        assert "p%40ss%2Fword" in dsn

    def test_build_dsn_vpc_nettype(self):
        """Test DSN with VPC nettype."""
        profile = {
            "name": "test",
            "endpoint": "",
            "instance_id": "hgprecn-cn-abc123",
            "region_id": "cn-hangzhou",
            "nettype": "vpc",
            "auth_mode": "ram",
            "access_key_id": "test",
            "access_key_secret": "secret",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "-vpc-st.hologres.aliyuncs.com" in dsn

    def test_build_dsn_no_password(self):
        """Test DSN without password."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "ram",
            "access_key_id": "test",
            "access_key_secret": "",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "test@host" in dsn
        assert ":@" not in dsn

    def test_build_dsn_sts_with_injected_credentials(self):
        """STS 模式：已注入临时凭证 → DSN 含 ?options=sts_token=..."""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "sts",
            "access_key_id": "STS.AKID",
            "access_key_secret": "secret",
            "security_token": "tok",
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        assert "STS.AKID" in dsn
        assert "secret" in dsn
        assert "?options=" in dsn

    def test_build_dsn_sts_options_roundtrip_special_chars(self):
        """头号回归测试：token 含 / + = 时，build_dsn → parse_dsn 往返完整还原。

        + 必须被 quote 成 %2B，否则 parse_qs 会把它当空格吞掉。
        """
        from hologres_cli.connection import parse_dsn

        token = "ab/cd+ef==gh"
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "sts",
            "access_key_id": "STS.AKID",
            "access_key_secret": "sk",
            "security_token": token,
            "database": "mydb",
            "port": 80,
        }
        dsn = build_dsn_from_profile(profile)
        params = parse_dsn(dsn)
        assert params["options"] == f"sts_token={token}"  # + 不丢、= 保留
        assert params["user"] == "STS.AKID"
        assert params["password"] == "sk"

    def test_build_dsn_sts_not_injected_raises(self):
        """STS 模式未注入临时凭证 → ConfigError（应由 get_connection 注入）。"""
        profile = {
            "name": "test",
            "endpoint": "host.example.com",
            "auth_mode": "sts",
            "database": "mydb",
            "port": 80,
        }
        with pytest.raises(ConfigError, match="未注入临时凭证"):
            build_dsn_from_profile(profile)


class TestMigrateFromLegacy:
    """Tests for migrate_from_legacy function."""

    def test_migrate_from_legacy_success(self, mock_home):
        """Test successful migration from config.env."""
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        legacy_file = config_dir / "config.env"
        legacy_file.write_text(
            "REGION_ID=cn-hangzhou\n"
            "INSTANCE_ID=hgprecn-cn-test\n"
            "ACCESS_KEY_ID=LTAI5tTest\n"
            "ACCESS_KEY_SECRET=Secret123\n"
            "DATABASE=testdb\n"
        )

        result = migrate_from_legacy()
        assert result is True

        config = load_config()
        assert config["current"] == "default"
        assert len(config["profiles"]) == 1
        assert config["profiles"][0]["region_id"] == "cn-hangzhou"
        assert config["profiles"][0]["auth_mode"] == "ram"

    def test_migrate_no_legacy_file(self, mock_home):
        """Test no migration when legacy file doesn't exist."""
        result = migrate_from_legacy()
        assert result is False

    def test_migrate_config_already_exists(self, mock_config):
        """Test no migration when config.json already exists."""
        # Create a legacy file too
        config_dir = mock_config.parent
        legacy_file = config_dir / "config.env"
        legacy_file.write_text("DATABASE=test\n")

        result = migrate_from_legacy()
        assert result is False

    def test_migrate_empty_legacy(self, mock_home):
        """Test no migration for empty legacy file."""
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        legacy_file = config_dir / "config.env"
        legacy_file.write_text("# comments only\n")

        result = migrate_from_legacy()
        assert result is False


class TestCredentialEncryption:
    """Tests for credential encryption in config storage."""

    def test_save_encrypts_sensitive_fields(self, mock_home, sample_config, monkeypatch):
        """save_config() writes encrypted values to disk."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: mock_home / ".hologres" / ".cipher_key")

        save_config(sample_config)

        # Read raw JSON from disk (bypass load_config decryption)
        config_file = mock_home / ".hologres" / "config.json"
        raw = json.loads(config_file.read_text())
        raw_profile = raw["profiles"][0]

        # Sensitive fields should be encrypted on disk
        assert raw_profile["access_key_secret"].startswith("ENC:")
        # Non-sensitive fields remain plain
        assert raw_profile["access_key_id"] == "LTAI5tTestAccessKeyId"

    def test_load_decrypts_sensitive_fields(self, mock_home, sample_config, monkeypatch):
        """load_config() returns decrypted values."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: mock_home / ".hologres" / ".cipher_key")

        save_config(sample_config)
        loaded = load_config()

        profile = loaded["profiles"][0]
        assert profile["access_key_secret"] == "TestAccessKeySecret123"

    def test_backward_compat_plaintext_config(self, mock_home, sample_config, monkeypatch):
        """Config with plaintext passwords still loads correctly."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: mock_home / ".hologres" / ".cipher_key")

        # Write plaintext config directly (simulating old format)
        config_dir = mock_home / ".hologres"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(sample_config, indent=2))

        loaded = load_config()
        profile = loaded["profiles"][0]
        assert profile["access_key_secret"] == "TestAccessKeySecret123"

    def test_save_does_not_mutate_original(self, mock_home, sample_config, monkeypatch):
        """save_config() does not modify the passed-in config dict."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: mock_home / ".hologres" / ".cipher_key")

        original_secret = sample_config["profiles"][0]["access_key_secret"]
        save_config(sample_config)

        assert sample_config["profiles"][0]["access_key_secret"] == original_secret

    def test_password_field_encrypted(self, mock_home, monkeypatch):
        """Password field (basic auth) is also encrypted."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: mock_home / ".hologres" / ".cipher_key")

        config = {
            "current": "basic-profile",
            "profiles": [{
                "name": "basic-profile",
                "auth_mode": "basic",
                "username": "BASIC$user",
                "password": "S3cr3t!@#$",
                "access_key_id": "",
                "access_key_secret": "",
                "region_id": "cn-hangzhou",
                "instance_id": "hgprecn-cn-xxx",
                "nettype": "internet",
                "database": "mydb",
                "warehouse": "default",
                "endpoint": "",
                "port": 80,
            }],
            "meta_path": "",
        }

        save_config(config)

        config_file = mock_home / ".hologres" / "config.json"
        raw = json.loads(config_file.read_text())
        assert raw["profiles"][0]["password"].startswith("ENC:")

        loaded = load_config()
        assert loaded["profiles"][0]["password"] == "S3cr3t!@#$"
