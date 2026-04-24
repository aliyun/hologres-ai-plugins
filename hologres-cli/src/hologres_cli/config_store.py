"""Configuration file I/O for Hologres CLI.

Manages multi-profile configuration stored in ~/.hologres/config.json.
All path resolution is done at runtime (via functions, not module-level constants)
to support test mocking of Path.home().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


# Endpoint templates for auto-construction from instance_id + region_id + nettype
ENDPOINT_TEMPLATES = {
    "internet": "{instance_id}-{region_id}.hologres.aliyuncs.com",
    "intranet": "{instance_id}-{region_id}-internal.hologres.aliyuncs.com",
    "vpc": "{instance_id}-{region_id}-vpc-st.hologres.aliyuncs.com",
}

# Default profile template
DEFAULT_PROFILE: dict[str, Any] = {
    "name": "default",
    "region_id": "cn-hangzhou",
    "instance_id": "",
    "nettype": "internet",
    "auth_mode": "ram",
    "access_key_id": "",
    "access_key_secret": "",
    "username": "",
    "password": "",
    "database": "",
    "warehouse": "init_warehouse",
    "endpoint": "",
    "port": 80,
    "output_format": "json",
    "language": "zh",
}

# Keys that can be set via `hologres config set <key> <value>`
SETTABLE_KEYS = {
    "region_id", "instance_id", "nettype", "auth_mode",
    "access_key_id", "access_key_secret", "username", "password",
    "database", "warehouse", "endpoint", "port",
    "output_format", "language",
}

# Sensitive keys that should be masked in display
SENSITIVE_KEYS = {"access_key_secret", "password"}


def _config_dir() -> Path:
    """Return the config directory path (~/.hologres). Evaluated at runtime."""
    return Path.home() / ".hologres"


def _config_file() -> Path:
    """Return the config file path (~/.hologres/config.json). Evaluated at runtime."""
    return _config_dir() / "config.json"


def _legacy_config_file() -> Path:
    """Return the legacy config file path (~/.hologres/config.env). Evaluated at runtime."""
    return _config_dir() / "config.env"


def load_config() -> dict[str, Any]:
    """Load configuration from config.json.

    Returns empty config structure if file doesn't exist.
    """
    config_file = _config_file()
    if not config_file.exists():
        return {"current": "", "profiles": [], "meta_path": ""}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ConfigError(f"Failed to read config file {config_file}: {e}")

    # Ensure required keys exist
    config.setdefault("current", "")
    config.setdefault("profiles", [])
    config.setdefault("meta_path", "")
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to config.json."""
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = _config_file()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError as e:
        raise ConfigError(f"Failed to write config file {config_file}: {e}")


def get_profile(name: str) -> dict[str, Any]:
    """Get a profile by name.

    Raises ConfigError if profile not found.
    """
    config = load_config()
    for profile in config.get("profiles", []):
        if profile.get("name") == name:
            return profile
    raise ConfigError(
        f"Profile '{name}' not found. "
        f"Run 'hologres config' to create one."
    )


def get_current_profile() -> dict[str, Any]:
    """Get the current active profile.

    Raises ConfigError if no current profile is set or profile not found.
    """
    config = load_config()
    current = config.get("current", "")
    if not current:
        raise ConfigError(
            "No current profile configured. "
            "Run 'hologres config' to set up your first profile."
        )
    return get_profile(current)


def set_profile(profile: dict[str, Any]) -> None:
    """Create or update a profile.

    If no current profile is set, this profile becomes current.
    """
    name = profile.get("name")
    if not name:
        raise ConfigError("Profile must have a 'name' field")

    config = load_config()
    profiles = config.get("profiles", [])

    # Update existing or append new
    found = False
    for i, p in enumerate(profiles):
        if p.get("name") == name:
            profiles[i] = profile
            found = True
            break

    if not found:
        profiles.append(profile)

    config["profiles"] = profiles

    # Set as current if no current profile exists
    if not config.get("current"):
        config["current"] = name

    save_config(config)


def delete_profile(name: str) -> None:
    """Delete a profile by name.

    Raises ConfigError if profile not found or is the last profile.
    """
    config = load_config()
    profiles = config.get("profiles", [])

    original_len = len(profiles)
    profiles = [p for p in profiles if p.get("name") != name]

    if len(profiles) == original_len:
        raise ConfigError(f"Profile '{name}' not found")

    config["profiles"] = profiles

    # Clear current if deleted profile was current
    if config.get("current") == name:
        config["current"] = profiles[0]["name"] if profiles else ""

    save_config(config)


def switch_profile(name: str) -> None:
    """Switch the current active profile.

    Raises ConfigError if profile not found.
    """
    # Verify profile exists
    get_profile(name)

    config = load_config()
    config["current"] = name
    save_config(config)


def list_profiles() -> list[dict[str, str]]:
    """List all profiles with summary info.

    Returns list of dicts with: name, region_id, instance_id, database, current (bool).
    """
    config = load_config()
    current = config.get("current", "")
    result = []
    for p in config.get("profiles", []):
        result.append({
            "name": p.get("name", ""),
            "region_id": p.get("region_id", ""),
            "instance_id": p.get("instance_id", ""),
            "database": p.get("database", ""),
            "current": "*" if p.get("name") == current else "",
        })
    return result


def mask_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the profile with sensitive fields masked."""
    masked = dict(profile)
    for key in SENSITIVE_KEYS:
        if masked.get(key):
            value = str(masked[key])
            if len(value) <= 4:
                masked[key] = "***"
            else:
                masked[key] = value[:3] + "*" * (len(value) - 6) + value[-3:]
    return masked


def build_dsn_from_profile(profile: dict[str, Any]) -> str:
    """Build a DSN string from a profile dict.

    DSN format: hologres://user:password@host:port/database

    Raises ConfigError if required fields are missing.
    """
    # Determine host
    endpoint = profile.get("endpoint", "")
    if endpoint:
        host = endpoint
    else:
        instance_id = profile.get("instance_id", "")
        region_id = profile.get("region_id", "")
        nettype = profile.get("nettype", "internet")

        if not instance_id:
            raise ConfigError(
                "Either 'endpoint' or 'instance_id' must be set. "
                "Run 'hologres config' to configure."
            )
        if not region_id:
            raise ConfigError(
                "Either 'endpoint' or 'region_id' must be set. "
                "Run 'hologres config' to configure."
            )

        template = ENDPOINT_TEMPLATES.get(nettype)
        if not template:
            raise ConfigError(
                f"Unknown nettype '{nettype}'. "
                f"Valid values: {', '.join(ENDPOINT_TEMPLATES.keys())}"
            )
        host = template.format(instance_id=instance_id, region_id=region_id)

    # Determine credentials
    auth_mode = profile.get("auth_mode", "ram")
    if auth_mode == "ram":
        user = profile.get("access_key_id", "")
        password = profile.get("access_key_secret", "")
        if not user:
            raise ConfigError(
                "access_key_id is required for RAM auth mode. "
                "Run 'hologres config' to configure."
            )
    elif auth_mode == "basic":
        user = profile.get("username", "")
        password = profile.get("password", "")
        if not user:
            raise ConfigError(
                "username is required for Basic auth mode. "
                "Run 'hologres config' to configure."
            )
    else:
        raise ConfigError(f"Unknown auth_mode '{auth_mode}'. Valid values: ram, basic")

    # Database
    database = profile.get("database", "")
    if not database:
        raise ConfigError(
            "database is required. Run 'hologres config' to configure."
        )

    # Port
    port = profile.get("port", 80)

    # URL-encode credentials for special characters
    user_encoded = quote(str(user), safe="")
    password_encoded = quote(str(password), safe="") if password else ""

    # Build DSN
    if password_encoded:
        dsn = f"hologres://{user_encoded}:{password_encoded}@{host}:{port}/{database}"
    else:
        dsn = f"hologres://{user_encoded}@{host}:{port}/{database}"

    return dsn


def migrate_from_legacy() -> bool:
    """Migrate from legacy config.env to config.json if needed.

    Returns True if migration was performed.
    """
    legacy_file = _legacy_config_file()
    config_file = _config_file()

    if not legacy_file.exists() or config_file.exists():
        return False

    try:
        # Parse legacy key=value format
        legacy_data: dict[str, str] = {}
        with open(legacy_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    legacy_data[key.strip()] = value.strip()

        if not legacy_data:
            return False

        # Map legacy fields to profile
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = "default"

        # Map known fields
        field_map = {
            "REGION_ID": "region_id",
            "INSTANCE_ID": "instance_id",
            "NETTYPE": "nettype",
            "ACCESS_KEY_ID": "access_key_id",
            "ACCESS_KEY_SECRET": "access_key_secret",
            "USERNAME": "username",
            "PASSWORD": "password",
            "DATABASE": "database",
            "WAREHOUSE": "warehouse",
            "ENDPOINT": "endpoint",
            "PORT": "port",
            "OUTPUT_FORMAT": "output_format",
            "LANGUAGE": "language",
        }

        for legacy_key, profile_key in field_map.items():
            if legacy_key in legacy_data:
                value = legacy_data[legacy_key]
                if profile_key == "port":
                    try:
                        value = int(value)
                    except ValueError:
                        continue
                profile[profile_key] = value

        # Determine auth_mode from available credentials
        if profile.get("access_key_id"):
            profile["auth_mode"] = "ram"
        elif profile.get("username"):
            profile["auth_mode"] = "basic"

        config = {
            "current": "default",
            "profiles": [profile],
            "meta_path": "",
        }
        save_config(config)
        return True
    except Exception:
        return False
