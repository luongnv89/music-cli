#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# music-cli Installer
# A command-line music player for coders: radio, local files, AI generation
#
# Quick install:
#   curl -sSL https://raw.githubusercontent.com/luongnv89/music-cli/main/install.sh | bash
#
# With optional extras:
#   EXTRAS=youtube curl -sSL https://raw.githubusercontent.com/luongnv89/music-cli/main/install.sh | bash
#   EXTRAS=ai      curl -sSL https://raw.githubusercontent.com/luongnv89/music-cli/main/install.sh | bash
#   EXTRAS="youtube,ai" curl -sSL https://raw.githubusercontent.com/luongnv89/music-cli/main/install.sh | bash
#
# Environment variables:
#   EXTRAS          Comma-separated optional extras: youtube, ai (default: none)
#   INSTALL_DIR     Virtual-env install location (default: ~/.local/share/music-cli)
#   PYTHON          Path to python interpreter to use (default: auto-detected)
#   SKIP_FFMPEG     Set to 1 to skip FFmpeg installation check
# ============================================================================

TOOL_NAME="music-cli"
PYPI_PACKAGE="coder-music-cli"
REPO="luongnv89/music-cli"
BRANCH="main"

EXTRAS="${EXTRAS:-}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/music-cli}"
SKIP_FFMPEG="${SKIP_FFMPEG:-0}"

# --- Color Output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${BLUE}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[ OK ]${NC}  %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
step()  { printf "\n${BOLD}${CYAN}==> %s${NC}\n" "$*"; }
err()   { printf "${RED}[ERR ]${NC}  %s\n" "$*" >&2; }
die()   { err "$@"; exit 1; }

# --- OS / Arch Detection ---
detect_os() {
    local os
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$os" in
        linux*)          echo "linux" ;;
        darwin*)         echo "macos" ;;
        mingw*|msys*|cygwin*) echo "windows" ;;
        *) die "Unsupported operating system: $os" ;;
    esac
}

detect_package_manager() {
    if command -v brew    &>/dev/null; then echo "brew"
    elif command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf   &>/dev/null; then echo "dnf"
    elif command -v yum   &>/dev/null; then echo "yum"
    elif command -v pacman &>/dev/null; then echo "pacman"
    elif command -v zypper &>/dev/null; then echo "zypper"
    else echo "unknown"
    fi
}

need_sudo() {
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo &>/dev/null; then echo "sudo"
        else echo ""   # caller will warn if sudo is needed
        fi
    else
        echo ""
    fi
}

# --- Dependency Checks ---
check_command() {
    command -v "$1" &>/dev/null
}

require_python() {
    # Honour explicit PYTHON override
    if [ -n "${PYTHON:-}" ]; then
        if ! "$PYTHON" --version &>/dev/null; then
            die "PYTHON='$PYTHON' is not executable"
        fi
        echo "$PYTHON"
        return
    fi

    for candidate in python3 python; do
        if check_command "$candidate"; then
            local ver
            ver="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
            local major minor
            major="${ver%%.*}"
            minor="${ver##*.}"
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$candidate"
                return
            fi
        fi
    done

    die "Python 3.10+ is required but was not found.
  Install it from https://www.python.org/downloads/ or via your package manager, then re-run this script."
}

install_ffmpeg() {
    local os="$1"
    local pm="$2"
    local sudo_cmd="$3"

    if check_command ffmpeg; then
        ok "FFmpeg already installed ($(ffmpeg -version 2>&1 | head -1 | awk '{print $3}'))"
        return
    fi

    info "Installing FFmpeg..."
    case "$os" in
        macos)
            if [ "$pm" = "brew" ]; then
                brew install ffmpeg
            else
                die "Homebrew is required to install FFmpeg on macOS.
  Install Homebrew: https://brew.sh
  Then re-run this script."
            fi
            ;;
        linux)
            case "$pm" in
                apt)    $sudo_cmd apt-get update -qq && $sudo_cmd apt-get install -y -qq ffmpeg ;;
                dnf)    $sudo_cmd dnf install -y -q ffmpeg ;;
                yum)    $sudo_cmd yum install -y -q ffmpeg ;;
                pacman) $sudo_cmd pacman -Sy --noconfirm ffmpeg ;;
                zypper) $sudo_cmd zypper install -y ffmpeg ;;
                *)
                    warn "Cannot auto-install FFmpeg (unknown package manager)."
                    warn "Please install FFmpeg manually: https://ffmpeg.org/download.html"
                    warn "Then re-run this script."
                    return 1
                    ;;
            esac
            ;;
        windows)
            warn "On Windows, please install FFmpeg manually."
            warn "Options:"
            warn "  winget install ffmpeg"
            warn "  choco install ffmpeg"
            warn "  Or download from: https://ffmpeg.org/download.html"
            warn "Then re-run this script."
            return 1
            ;;
    esac
    ok "FFmpeg installed"
}

install_pip_if_needed() {
    local python="$1"
    if ! "$python" -m pip --version &>/dev/null; then
        info "pip not found — installing via ensurepip..."
        "$python" -m ensurepip --upgrade || die "Failed to install pip. Install it manually: https://pip.pypa.io/en/stable/installation/"
    fi
}

# --- Main music-cli Install ---
install_music_cli() {
    local python="$1"

    step "Creating isolated environment at $INSTALL_DIR"
    "$python" -m venv "$INSTALL_DIR"
    local venv_python="$INSTALL_DIR/bin/python"
    local venv_pip="$INSTALL_DIR/bin/pip"

    step "Upgrading pip inside venv"
    "$venv_pip" install --quiet --upgrade pip

    # Build extras specifier
    local pkg="$PYPI_PACKAGE"
    if [ -n "$EXTRAS" ]; then
        pkg="${PYPI_PACKAGE}[$EXTRAS]"
    fi

    step "Installing $pkg from PyPI"
    # Upgrade an existing venv as well as installing into a new one. Without
    # --upgrade, pip can leave an older music-cli package in place and the
    # linked mc command will keep running stale code.
    "$venv_python" -m pip install --quiet --upgrade "$pkg"
    ok "Installed $pkg"
}

# --- Symlink / PATH setup ---
link_binary() {
    mkdir -p "$HOME/.local/bin"

    for cmd in music-cli mc; do
        local venv_bin="$INSTALL_DIR/bin/$cmd"
        local link_target="$HOME/.local/bin/$cmd"

        if [ -L "$link_target" ] || [ -f "$link_target" ]; then
            rm -f "$link_target"
        fi
        ln -s "$venv_bin" "$link_target"
        ok "Linked $link_target -> $venv_bin"
    done

    # Shell PATH advice
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        warn "'$HOME/.local/bin' is not in your PATH."
        warn "Add the following line to your shell profile (~/.bashrc / ~/.zshrc):"
        warn ""
        warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        warn ""
        warn "Then reload: source ~/.bashrc   (or open a new terminal)"
    fi
}

# --- Verification ---
verify_installation() {
    local venv_bin="$INSTALL_DIR/bin/music-cli"
    step "Verifying installation"
    if [ -x "$venv_bin" ]; then
        local ver
        ver="$("$venv_bin" --version 2>/dev/null || true)"
        ok "$TOOL_NAME $ver is ready"
    else
        die "Installation verification failed — $venv_bin not found or not executable"
    fi
}

# --- Entry Point ---
main() {
    printf "\n${BOLD}${GREEN}music-cli installer${NC}\n"
    printf "${CYAN}  Code. Listen. Iterate.${NC}\n\n"
    printf "  Repo    : https://github.com/$REPO\n"
    printf "  PyPI    : https://pypi.org/project/$PYPI_PACKAGE\n"
    printf "  Extras  : ${EXTRAS:-none}\n"
    printf "  Dest    : $INSTALL_DIR\n\n"

    local os pm sudo_cmd python
    os="$(detect_os)"
    pm="$(detect_package_manager)"
    sudo_cmd="$(need_sudo)"

    info "Platform: $os | Package manager: $pm"

    # ── Python ──────────────────────────────────────────────
    step "Checking Python 3.10+"
    python="$(require_python)"
    ok "Using Python: $python ($("$python" --version))"

    # ── pip ─────────────────────────────────────────────────
    step "Checking pip"
    install_pip_if_needed "$python"
    ok "pip available"

    # ── FFmpeg ──────────────────────────────────────────────
    if [ "$SKIP_FFMPEG" = "0" ]; then
        step "Checking FFmpeg"
        if ! install_ffmpeg "$os" "$pm" "$sudo_cmd"; then
            warn "FFmpeg installation skipped. music-cli requires FFmpeg for audio playback."
            warn "Install it manually and ensure it is in your PATH before using music-cli."
        fi
    else
        warn "Skipping FFmpeg check (SKIP_FFMPEG=1)"
    fi

    # ── music-cli ────────────────────────────────────────────
    install_music_cli "$python"

    # ── Symlink ──────────────────────────────────────────────
    step "Setting up PATH"
    link_binary

    # ── Done ─────────────────────────────────────────────────
    verify_installation

    printf "\n${BOLD}${GREEN}============================================${NC}\n"
    ok "Installation complete!"
    printf "${BOLD}${GREEN}============================================${NC}\n\n"
    printf "  Get started:\n\n"
    printf "    ${CYAN}music-cli play${NC}              # context-aware radio\n"
    printf "    ${CYAN}music-cli play --mood focus${NC} # focus music\n"
    printf "    ${CYAN}music-cli status${NC}            # what's playing\n"
    printf "    ${CYAN}music-cli --help${NC}            # all commands\n\n"

    if [ -n "$EXTRAS" ]; then
        printf "  Extras installed: ${YELLOW}$EXTRAS${NC}\n"
        if echo "$EXTRAS" | grep -q "ai"; then
            printf "    AI models are downloaded on first use (~1.5–6 GB each).\n"
            printf "    Try: ${CYAN}music-cli ai play --mood focus${NC}\n"
        fi
        if echo "$EXTRAS" | grep -q "youtube"; then
            printf "    YouTube streaming is ready.\n"
            printf "    Try: ${CYAN}music-cli play -m youtube -s \"<URL>\"${NC}\n"
        fi
    fi
    printf "\n"
}

main "$@"
