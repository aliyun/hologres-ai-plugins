#!/usr/bin/env python3
"""Main entry point for Hologres plugin installer."""

import sys
import shutil
from pathlib import Path
from typing import Dict, List

try:
    import questionary
    from questionary import Choice, Style
except ImportError:
    print("Error: questionary is not installed. Please install it with: pip install questionary")
    sys.exit(1)


# Custom style: no background for selected/highlighted items in checkbox/select.
# prompt_toolkit's default_ui_style uses ("selected", "reverse"); we override with noreverse.
_NO_BG_STYLE = Style([
    ("selected", "noreverse"),
    ("highlighted", "noreverse"),
])


# Tool configurations: tool name -> skills directory path
TOOL_CONFIGS: Dict[str, str] = {
    "Claude Code": ".claude/skills",
    "OpenClaw": "~/.openclaw/workspace/skills",
    "Cursor": ".cursor/skills",
    "Codex": ".agents/skills",
    "OpenCode": ".opencode/skills",
    "GitHub Copilot": ".github/skills",
    "Qoder": ".qoder/skills",
    "Trae": ".trae/skills",
}

# Available skills to install
AVAILABLE_SKILLS = [
    "hologres-cli",
    "hologres-query-optimizer",
    "hologres-slow-query-analysis",
    "hologres-schema-generator",
    "hologres-privileges",
    "hologres-uv-compute",
    "hologres-bsi-profile-analysis",
]


def get_package_skills_dir() -> Path:
    package_dir = Path(__file__).parent
    # After installation: skills/ in package
    if (package_dir / "skills").exists():
        return package_dir / "skills"
    # During development: project root skills/ (package is in src/holo_plugin_installer/)
    root_skills = package_dir.parent.parent / "skills"
    if root_skills.exists():
        return root_skills
    raise FileNotFoundError("Skills directory not found")


def get_tool_skills_path(tool_name: str, project_root: Path) -> Path:
    """Get the full path to the skills directory for a given tool."""
    skills_dir_name = TOOL_CONFIGS.get(tool_name)
    if not skills_dir_name:
        raise ValueError(f"Unknown tool: {tool_name}")
    path = Path(skills_dir_name)
    if skills_dir_name.startswith("~"):
        return path.expanduser()
    return project_root / skills_dir_name


def is_global_tool_path(tool_name: str) -> bool:
    """True if this tool uses a global/user path (e.g. ~/.openclaw/...) instead of project-relative path."""
    path = TOOL_CONFIGS.get(tool_name, "")
    return path.startswith("~")


def copy_skill(source_skill_dir: Path, target_skills_dir: Path, skill_name: str) -> bool:
    """Copy a skill directory to the target location."""
    target_skill_dir = target_skills_dir / skill_name

    try:
        # Remove existing skill if it exists
        if target_skill_dir.exists():
            shutil.rmtree(target_skill_dir)

        # Create parent directory if it doesn't exist
        target_skills_dir.mkdir(parents=True, exist_ok=True)

        # Copy the skill directory
        shutil.copytree(source_skill_dir, target_skill_dir)

        return True
    except Exception as e:
        print(f"Error copying skill {skill_name}: {e}")
        return False


def install_skills(tools: List[str], skills: List[str], project_root: Path) -> None:
    """Install selected skills to selected tools."""
    package_skills_dir = get_package_skills_dir()

    if not package_skills_dir.exists():
        print(f"Error: Skills directory not found at {package_skills_dir}")
        print("Please ensure the package is properly installed.")
        sys.exit(1)

    print(f"\n📦 Skills source: {package_skills_dir}")
    if any(not is_global_tool_path(t) for t in tools):
        print(f"📁 Project root: {project_root}")
    print()

    for tool in tools:
        tool_skills_path = get_tool_skills_path(tool, project_root)
        print(f"🔧 Installing to {tool} ({tool_skills_path})...")

        for skill in skills:
            source_skill_dir = package_skills_dir / skill
            if not source_skill_dir.exists():
                print(f"  ⚠️  Skill '{skill}' not found, skipping...")
                continue

            if copy_skill(source_skill_dir, tool_skills_path, skill):
                print(f"  ✅ Installed '{skill}'")
            else:
                print(f"  ❌ Failed to install '{skill}'")

        print()


def main():
    """Main entry point for the installer."""
    try:
        print("🚀 Hologres Agent Skills Installer")
        print("=" * 50)

        # Select tool first (path type affects project root prompt)
        print("\n📋 Select tool to install to:")
        try:
            selected_tool = questionary.select(
                "Select one tool (use ↑↓ to navigate, Enter to confirm, Ctrl+C to cancel):",
                choices=list(TOOL_CONFIGS.keys()),
                style=_NO_BG_STYLE,
            ).ask()
        except KeyboardInterrupt:
            print("\n\nInstallation cancelled by user.")
            sys.exit(0)

        if not selected_tool:
            print("No tool selected. Exiting.")
            sys.exit(0)
        selected_tools = [selected_tool]

        # Confirm install path: project-relative vs global (e.g. OpenClaw)
        project_root = Path.cwd()
        if is_global_tool_path(selected_tool):
            install_path = get_tool_skills_path(selected_tool, project_root)
            print(f"\n📁 Skills will be installed to: {install_path}")
            try:
                confirm = questionary.confirm("Continue?", default=True).ask()
            except KeyboardInterrupt:
                print("\n\nInstallation cancelled by user.")
                sys.exit(0)
            if not confirm:
                print("Installation cancelled.")
                sys.exit(0)
        else:
            print(f"\n📁 Project root: {project_root}")
            print(f"   (Skills will be installed under {TOOL_CONFIGS[selected_tool]})")
            try:
                confirm_root = questionary.confirm(
                    "Install skills to this directory?",
                    default=True
                ).ask()
            except KeyboardInterrupt:
                print("\n\nInstallation cancelled by user.")
                sys.exit(0)
            if not confirm_root:
                print("Installation cancelled.")
                sys.exit(0)

        # Select skills
        print("\n📦 Select skills to install:")
        try:
            selected_skills = questionary.checkbox(
                "Select skills (use ↑↓ to navigate, Space to select, Enter to confirm, Ctrl+C to cancel):",
                choices=[
                    questionary.Choice("hologres-cli", checked=True),
                    "hologres-query-optimizer",
                    "hologres-slow-query-analysis",
                    "hologres-privileges",
                    "hologres-uv-compute",
                    "hologres-schema-generator",
                ],
                instruction="(Select multiple with Space)",
                style=_NO_BG_STYLE,
            ).ask()
        except KeyboardInterrupt:
            print("\n\nInstallation cancelled by user.")
            sys.exit(0)

        if not selected_skills:
            print("No skills selected. Exiting.")
            sys.exit(0)

        # Installation summary
        print("\n📝 Installation Summary:")
        print(f"  Tools: {', '.join(selected_tools)}")
        print(f"  Skills: {', '.join(selected_skills)}")
        if not all(is_global_tool_path(t) for t in selected_tools):
            print(f"  Project root: {project_root}")

        # Install skills
        install_skills(selected_tools, selected_skills, project_root)

        print("✨ Installation complete")
        print("\n💡 Please verify the skills are available in your tool's skill directory")
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
