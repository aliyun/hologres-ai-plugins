"""Configuration management commands for Hologres CLI.

Provides interactive setup, get/set/list/show/delete/switch/current subcommands
for managing multi-profile configuration.
"""

from __future__ import annotations

import click

from ..config_store import (
    ConfigError,
    DEFAULT_PROFILE,
    SETTABLE_KEYS,
    build_dsn_from_profile,
    delete_profile,
    get_current_profile,
    get_profile,
    list_profiles,
    load_config,
    mask_profile,
    migrate_from_legacy,
    set_profile,
    switch_profile,
)
from ..output import FORMAT_JSON, error, print_output, success, success_rows


# Success banner from configure.md
CONFIGURE_DONE_BANNER = """\
..............888888888888888888888 ........=8888888888888888888D=..............
...........88888888888888888888888 ..........D8888888888888888888888I...........
.........,8888888888888ZI: ...........................=Z88D8888888888D..........
.........+88888888 ..........................................88888888D..........
.........+88888888 .......Welcome to use Alibaba Hologres .......O8888888D......
.........+88888888 ............. ************* ..............O8888888D..........
.........+88888888 .... Command Line Interface(Reloaded) ....O8888888D..........
.........+88888888...........................................88888888D..........
..........D888888888888DO+. ..........................?ND888888888888D..........
...........O8888888888888888888888...........D8888888888888888888888=...........
............ .:D8888888888888888888.........78888888888888888888O .............."""


# Interactive wizard choices
REGION_CHOICES = [
    "cn-hangzhou", "cn-shanghai", "cn-beijing", "cn-shenzhen",
    "cn-hongkong", "cn-zhangjiakou", "cn-huhehaote", "cn-chengdu",
    "ap-southeast-1", "ap-southeast-3", "ap-southeast-5",
    "us-west-1", "us-east-1", "eu-central-1",
]
NETTYPE_CHOICES = ["internet", "intranet", "vpc"]
AUTH_MODE_CHOICES = ["ram", "basic"]
LANGUAGE_CHOICES = ["zh", "en"]


@click.group("config", invoke_without_command=True)
@click.option("--profile", "-p", default=None, help="Profile name to configure (default: 'default')")
@click.pass_context
def config_cmd(ctx: click.Context, profile: str) -> None:
    """Manage Hologres CLI configuration.

    \b
    Run without subcommand to start interactive setup wizard.
    Subcommands: set, get, list, show, delete, switch, current

    \b
    Examples:
      hologres config                    # Interactive wizard
      hologres config --profile prod     # Configure 'prod' profile
      hologres config list               # List all profiles
      hologres config switch prod        # Switch to 'prod' profile
    """
    if ctx.invoked_subcommand is None:
        _interactive_wizard(profile or "default")


def _interactive_wizard(profile_name: str) -> None:
    """Run the interactive configuration wizard."""
    # Check for legacy config migration
    if migrate_from_legacy():
        click.echo("Migrated legacy config.env to config.json")

    # Load existing profile or use defaults
    try:
        existing = get_profile(profile_name)
    except ConfigError:
        existing = dict(DEFAULT_PROFILE)
        existing["name"] = profile_name

    click.echo(f"Configuring profile '{profile_name}'...")
    click.echo()

    # Region
    region_display = ", ".join(REGION_CHOICES[:3]) + ", ..."
    region_id = click.prompt(
        f"Region Id [{region_display}]",
        default=existing.get("region_id", "cn-hangzhou"),
    )

    # Instance ID
    instance_id = click.prompt(
        "Instance Id",
        default=existing.get("instance_id", ""),
    )

    # Network type
    nettype = click.prompt(
        f"Network type [{'/'.join(NETTYPE_CHOICES)}]",
        type=click.Choice(NETTYPE_CHOICES, case_sensitive=False),
        default=existing.get("nettype", "internet"),
    )

    # Auth mode
    auth_mode = click.prompt(
        f"Auth mode [{'/'.join(AUTH_MODE_CHOICES)}]",
        type=click.Choice(AUTH_MODE_CHOICES, case_sensitive=False),
        default=existing.get("auth_mode", "ram"),
    )

    # Credentials based on auth mode
    access_key_id = existing.get("access_key_id", "")
    access_key_secret = existing.get("access_key_secret", "")
    username = existing.get("username", "")
    password = existing.get("password", "")

    if auth_mode == "ram":
        access_key_id = click.prompt(
            "Access Key Id",
            default=access_key_id,
        )
        access_key_secret = click.prompt(
            "Access Key Secret",
            default="",
            hide_input=True,
            show_default=False,
        )
        if not access_key_secret:
            access_key_secret = existing.get("access_key_secret", "")
    else:
        username = click.prompt(
            "Username",
            default=username,
        )
        password = click.prompt(
            "Password",
            default="",
            hide_input=True,
            show_default=False,
        )
        if not password:
            password = existing.get("password", "")

    # Database
    database = click.prompt(
        "Database",
        default=existing.get("database", ""),
    )

    # Warehouse
    warehouse = click.prompt(
        "Warehouse",
        default=existing.get("warehouse", "init_warehouse"),
    )

    # Optional: direct endpoint override
    endpoint = click.prompt(
        "Endpoint (leave empty to auto-construct from Instance Id)",
        default=existing.get("endpoint", ""),
    )

    # Port
    port_default = existing.get("port", 80)
    port = click.prompt(
        "Port",
        default=port_default,
        type=int,
    )

    # Language
    language = click.prompt(
        f"Language [{'/'.join(LANGUAGE_CHOICES)}]",
        type=click.Choice(LANGUAGE_CHOICES, case_sensitive=False),
        default=existing.get("language", "zh"),
    )

    # Build profile
    profile = {
        "name": profile_name,
        "region_id": region_id,
        "instance_id": instance_id,
        "nettype": nettype,
        "auth_mode": auth_mode,
        "access_key_id": access_key_id,
        "access_key_secret": access_key_secret,
        "username": username,
        "password": password,
        "database": database,
        "warehouse": warehouse,
        "endpoint": endpoint,
        "port": port,
        "output_format": "json",
        "language": language,
    }

    # Validate by building DSN
    try:
        dsn = build_dsn_from_profile(profile)
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e)))
        return

    # Save
    set_profile(profile)
    click.echo()
    click.echo(f"Saving profile [{profile_name}] ... Done.")
    click.echo()
    click.echo("Configure Done!!!")
    click.echo(CONFIGURE_DONE_BANNER)
    click.echo()
    click.echo(f"  Profile:  {profile_name}")
    click.echo(f"  Endpoint: {endpoint or '(auto-constructed)'}")
    click.echo(f"  Database: {database}")
    click.echo(f"  Auth:     {auth_mode}")


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--profile", "-p", default=None, help="Target profile (default: current)")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str, profile: str) -> None:
    """Set a configuration value.

    \b
    Examples:
      hologres config set database mydb
      hologres config set region_id cn-shanghai --profile prod
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        if key not in SETTABLE_KEYS:
            print_output(error("CONFIG_ERROR",
                               f"Unknown key '{key}'. Valid keys: {', '.join(sorted(SETTABLE_KEYS))}",
                               fmt))
            return

        profile_name = profile
        if not profile_name:
            config = load_config()
            profile_name = config.get("current", "")
            if not profile_name:
                print_output(error("CONFIG_ERROR", "No current profile. Run 'hologres config' first.", fmt))
                return

        p = get_profile(profile_name)

        # Type conversion for port
        if key == "port":
            try:
                value = int(value)
            except ValueError:
                print_output(error("CONFIG_ERROR", f"Invalid port value: {value}", fmt))
                return

        p[key] = value
        set_profile(p)
        print_output(success({"profile": profile_name, "key": key, "value": value if key not in ("access_key_secret", "password") else "***"}, fmt))
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e), fmt))


@config_cmd.command("get")
@click.argument("key")
@click.option("--profile", "-p", default=None, help="Target profile (default: current)")
@click.pass_context
def config_get(ctx: click.Context, key: str, profile: str) -> None:
    """Get a configuration value.

    \b
    Examples:
      hologres config get database
      hologres config get region_id --profile prod
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        profile_name = profile
        if not profile_name:
            config = load_config()
            profile_name = config.get("current", "")
            if not profile_name:
                print_output(error("CONFIG_ERROR", "No current profile. Run 'hologres config' first.", fmt))
                return

        p = get_profile(profile_name)
        if key not in p:
            print_output(error("CONFIG_ERROR", f"Unknown key '{key}'", fmt))
            return

        value = p[key]
        if key in ("access_key_secret", "password") and value:
            value = "***"

        print_output(success({"profile": profile_name, "key": key, "value": value}, fmt))
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e), fmt))


@config_cmd.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """List all configured profiles.

    \b
    Examples:
      hologres config list
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    profiles = list_profiles()
    print_output(success_rows(profiles, fmt))


@config_cmd.command("show")
@click.option("--profile", "-p", default=None, help="Profile to show (default: current)")
@click.pass_context
def config_show(ctx: click.Context, profile: str) -> None:
    """Show full profile configuration (sensitive fields masked).

    \b
    Examples:
      hologres config show
      hologres config show --profile prod
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        if profile:
            p = get_profile(profile)
        else:
            p = get_current_profile()

        masked = mask_profile(p)
        print_output(success(masked, fmt))
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e), fmt))


@config_cmd.command("delete")
@click.argument("profile_name")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def config_delete(ctx: click.Context, profile_name: str, confirm: bool) -> None:
    """Delete a profile.

    \b
    Examples:
      hologres config delete old-profile --confirm
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    if not confirm:
        print_output(error("CONFIRMATION_REQUIRED",
                           f"Add --confirm to delete profile '{profile_name}'", fmt))
        return

    try:
        delete_profile(profile_name)
        print_output(success({"deleted": profile_name}, fmt))
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e), fmt))


@config_cmd.command("switch")
@click.argument("profile_name")
@click.pass_context
def config_switch(ctx: click.Context, profile_name: str) -> None:
    """Switch the current active profile.

    \b
    Examples:
      hologres config switch prod
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    try:
        switch_profile(profile_name)
        print_output(success({"current": profile_name}, fmt))
    except ConfigError as e:
        print_output(error("CONFIG_ERROR", str(e), fmt))


@config_cmd.command("current")
@click.pass_context
def config_current(ctx: click.Context) -> None:
    """Show the current active profile name.

    \b
    Examples:
      hologres config current
    """
    fmt = ctx.obj.get("format", FORMAT_JSON)
    config = load_config()
    current = config.get("current", "")
    if not current:
        print_output(error("CONFIG_ERROR", "No current profile. Run 'hologres config' first.", fmt))
    else:
        print_output(success({"current": current}, fmt))
