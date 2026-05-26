#!/bin/sh
# Hologres Agent Skills - One-Line Installer
# Usage: curl -sSf https://raw.githubusercontent.com/aliyun/hologres-ai-plugins/master/agent-skills/install.sh | sh
#
# Installs the hologres-agent-skills interactive installer, then launches it
# so you can select which skills to install and which AI tool to target.
#
# Environment variables:
#   HOLOGRES_INSTALL_DIR    Custom install directory (default: ~/.local/bin)
#   HOLOGRES_NO_LAUNCH=1   Install only, don't auto-launch the skill selector

set -e

# ── Constants ────────────────────────────────────────────────────────────────
VERSION="0.2.1"
PACKAGE="hologres-agent-skills"
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

# ── Helper functions ─────────────────────────────────────────────────────────

info()    { printf "${CYAN}[INFO]${RESET} %s\n" "$1"; }
success() { printf "${GREEN}[OK]${RESET}   %s\n" "$1"; }
warn()    { printf "${YELLOW}[WARN]${RESET} %s\n" "$1"; }
error()   { printf "${RED}[ERROR]${RESET} %s\n" "$1" >&2; }
die()     { error "$1"; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ── Detect environment ───────────────────────────────────────────────────────

detect_os() {
    case "$(uname -s)" in
        Linux*)   echo "linux" ;;
        Darwin*)  echo "macos" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)        echo "unknown" ;;
    esac
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)  echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        *)             echo "unknown" ;;
    esac
}

detect_shell() {
    if [ -n "$SHELL" ]; then
        basename "$SHELL"
    else
        echo "sh"
    fi
}

get_shell_profile() {
    local shell_name
    shell_name=$(detect_shell)
    case "$shell_name" in
        bash)
            if [ -f "$HOME/.bash_profile" ]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        zsh)  echo "$HOME/.zshrc" ;;
        fish) echo "$HOME/.config/fish/config.fish" ;;
        *)    echo "$HOME/.profile" ;;
    esac
}

# ── Python detection ─────────────────────────────────────────────────────────

find_python3() {
    for cmd in python3 python3.13 python3.12 python3.11 python3.10; do
        if command_exists "$cmd"; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            if [ $? -eq 0 ]; then
                local major minor
                major=$(echo "$ver" | cut -d. -f1)
                minor=$(echo "$ver" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                    echo "$cmd"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# ── Install uv ───────────────────────────────────────────────────────────────

install_uv() {
    if command_exists uv; then
        success "uv is already installed: $(uv --version)"
        return 0
    fi

    if [ -x "$HOME/.local/bin/uv" ]; then
        UV_BIN="$HOME/.local/bin/uv"
        success "uv found at ~/.local/bin/uv"
        return 0
    fi

    if [ -x "$HOME/.cargo/bin/uv" ]; then
        UV_BIN="$HOME/.cargo/bin/uv"
        success "uv found at ~/.cargo/bin/uv"
        return 0
    fi

    info "Installing uv (Python package manager)..."
    if command_exists curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command_exists wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        die "Neither curl nor wget found. Please install one first."
    fi

    if [ -x "$HOME/.local/bin/uv" ]; then
        UV_BIN="$HOME/.local/bin/uv"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        UV_BIN="$HOME/.cargo/bin/uv"
    else
        die "uv installation succeeded but binary not found."
    fi

    success "uv installed successfully"
}

# ── Configure PATH ───────────────────────────────────────────────────────────

configure_path() {
    local install_dir="${HOLOGRES_INSTALL_DIR:-$HOME/.local/bin}"
    local shell_profile
    shell_profile=$(get_shell_profile)

    case ":$PATH:" in
        *":$install_dir:"*)
            success "PATH already includes $install_dir"
            return 0
            ;;
    esac

    info "Adding $install_dir to PATH..."

    local shell_name
    shell_name=$(detect_shell)

    local path_line
    if [ "$shell_name" = "fish" ]; then
        path_line="fish_add_path $install_dir"
    else
        path_line="export PATH=\"$install_dir:\$PATH\""
    fi

    if [ -f "$shell_profile" ] && grep -qF "$install_dir" "$shell_profile" 2>/dev/null; then
        success "PATH entry already exists in $shell_profile"
    else
        printf "\n# Added by Hologres Agent Skills installer\n%s\n" "$path_line" >> "$shell_profile"
        success "Added PATH to $shell_profile"
    fi

    export PATH="$install_dir:$PATH"
}

# ── Install package ──────────────────────────────────────────────────────────

install_package() {
    info "Installing $PACKAGE..."

    local uv_cmd="${UV_BIN:-uv}"

    "$uv_cmd" tool install --force "$PACKAGE" 2>&1 || {
        warn "uv tool install failed, trying pip..."
        local python_cmd
        python_cmd=$(find_python3) || die "No Python 3.10+ found. Please install Python first."
        "$python_cmd" -m pip install --user "$PACKAGE" || die "Failed to install $PACKAGE"
    }

    success "$PACKAGE installed successfully"
}

# ── Verify ───────────────────────────────────────────────────────────────────

verify_installation() {
    printf "\n"
    info "Verifying installation..."

    if command_exists hologres-agent-skills; then
        success "hologres-agent-skills: ready"
    elif [ -x "$HOME/.local/bin/hologres-agent-skills" ]; then
        success "hologres-agent-skills: installed at ~/.local/bin/"
    else
        warn "hologres-agent-skills not found (restart shell or source profile)"
    fi
}

# ── Launch installer ─────────────────────────────────────────────────────────

launch_installer() {
    if [ "${HOLOGRES_NO_LAUNCH:-0}" = "1" ]; then
        info "Skipping auto-launch (HOLOGRES_NO_LAUNCH=1)"
        return 0
    fi

    printf "\n"
    printf "${BOLD}Launching skill installer...${RESET}\n"
    printf "\n"

    if command_exists hologres-agent-skills; then
        hologres-agent-skills
    elif [ -x "$HOME/.local/bin/hologres-agent-skills" ]; then
        "$HOME/.local/bin/hologres-agent-skills"
    else
        warn "Cannot auto-launch. Please run manually: hologres-agent-skills"
    fi
}

# ── Summary (shown if no auto-launch) ────────────────────────────────────────

print_summary() {
    local shell_profile
    shell_profile=$(get_shell_profile)

    printf "\n"
    printf "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}\n"
    printf "${BOLD}${GREEN}  ✨ Hologres Agent Skills - Installation Complete${RESET}\n"
    printf "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}\n"
    printf "\n"
    printf "${BOLD}Usage:${RESET}\n"
    printf "\n"
    printf "  ${CYAN}hologres-agent-skills${RESET}\n"
    printf "\n"
    printf "  This will interactively install skills to your AI tool:\n"
    printf "  Claude Code, Cursor, Codex, GitHub Copilot, Qoder, Trae, etc.\n"
    printf "\n"
    printf "${BOLD}Available Skills:${RESET}\n"
    printf "  • hologres-cli              (CLI usage guide)\n"
    printf "  • hologres-query-optimizer  (Query plan analysis)\n"
    printf "  • hologres-slow-query-analysis (Slow query diagnosis)\n"
    printf "  • hologres-schema-generator (DDL design expert)\n"
    printf "  • hologres-privileges       (Permission management)\n"
    printf "  • hologres-uv-compute       (UV/PV deduplication)\n"
    printf "  • hologres-bsi-profile-analysis (BSI user profiles)\n"
    printf "  • hologres-ad-campaign      (Ad creative & campaign)\n"
    printf "  • hologres-instance-health-analyse (Instance health diagnosis)\n"
    printf "  • hologres-diagnosis-cpu      (CPU anomaly diagnosis)\n"
    printf "\n"
    printf "${BOLD}Prerequisite:${RESET} Install hologres-cli first if not already:\n"
    printf "  ${CYAN}curl -sSf https://raw.githubusercontent.com/aliyun/hologres-ai-plugins/master/hologres-cli/install.sh | sh${RESET}\n"
    printf "\n"
    printf "${BOLD}Docs:${RESET} https://github.com/aliyun/hologres-ai-plugins/tree/master/agent-skills\n"
    printf "\n"
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
    printf "\n"
    printf "${BOLD}${CYAN}══════════════════════════════════════════════════${RESET}\n"
    printf "${BOLD}${CYAN}  Hologres Agent Skills Installer v%s${RESET}\n" "$VERSION"
    printf "${BOLD}${CYAN}══════════════════════════════════════════════════${RESET}\n"
    printf "\n"

    local os arch
    os=$(detect_os)
    arch=$(detect_arch)
    info "Detected: OS=$os, Arch=$arch, Shell=$(detect_shell)"

    [ "$os" = "unknown" ] && die "Unsupported OS: $(uname -s)"

    UV_BIN=""
    install_uv
    configure_path
    install_package
    verify_installation

    if [ "${HOLOGRES_NO_LAUNCH:-0}" = "1" ]; then
        print_summary
    else
        launch_installer
    fi
}

main "$@"
