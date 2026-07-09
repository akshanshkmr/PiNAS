#!/usr/bin/env bash
#
# PiNAS one-line installer.
#
# Usage (on a fresh Raspberry Pi):
#     curl -fsSL https://raw.githubusercontent.com/akshanshkmr/PiNAS/main/install.sh | bash
#
# What it does:
#   - Installs git via apt if it's missing
#   - Clones (or updates) the PiNAS repo
#   - Hands off to setup.sh, which installs everything else
#
# Env overrides:
#   PINAS_DIR   Clone destination        (default: $HOME/PiNAS)
#   PINAS_REF   Git ref to check out     (default: main)
#   PINAS_REPO  Repo URL                 (default: the official one)
#
# Setup env vars (SETUP_ENABLE_NOPASSWD_SUDO, SETUP_FULL_UPGRADE, ...) are
# passed straight through to setup.sh.

set -euo pipefail

REPO_URL="${PINAS_REPO:-https://github.com/akshanshkmr/PiNAS.git}"
TARGET="${PINAS_DIR:-$HOME/PiNAS}"
REF="${PINAS_REF:-main}"

# colours (skipped when not attached to a terminal)
if [ -t 1 ]; then
    BOLD=$'\e[1m'; BLUE=$'\e[1;34m'; GREEN=$'\e[1;32m'; YELLOW=$'\e[1;33m'; DIM=$'\e[0;90m'; NC=$'\e[0m'
else
    BOLD=""; BLUE=""; GREEN=""; YELLOW=""; DIM=""; NC=""
fi
log()  { printf "\n%s==>%s %s%s%s\n" "$BLUE" "$NC" "$BOLD" "$*" "$NC"; }
ok()   { printf "    %s✓%s %s\n" "$GREEN" "$NC" "$*"; }
warn() { printf "    %s!%s %s\n" "$YELLOW" "$NC" "$*"; }
say()  { printf "    %s%s%s\n" "$DIM" "$*" "$NC"; }

cat <<'BANNER'

    ██████╗ ██╗   ███╗   ██╗ █████╗ ███████╗
    ██╔══██╗██║   ████╗  ██║██╔══██╗██╔════╝
    ██████╔╝██║   ██╔██╗ ██║███████║███████╗
    ██╔═══╝ ██║   ██║╚██╗██║██╔══██║╚════██║
    ██║     ██║██╗██║ ╚████║██║  ██║███████║
    ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝

    a self-hosted dashboard + nas for the raspberry pi

BANNER

if ! command -v sudo >/dev/null 2>&1; then
    printf "PiNAS needs sudo to install packages. Install sudo and re-run.\n" >&2
    exit 1
fi

# ------------------------------------------------------------
log "Ensuring git is installed"
if ! command -v git >/dev/null 2>&1; then
    say "git not found — installing via apt"
    sudo apt-get update
    sudo apt-get install -y git ca-certificates curl
    ok "git $(git --version | awk '{print $3}')"
else
    ok "git $(git --version | awk '{print $3}') already installed"
fi

# ------------------------------------------------------------
log "Fetching PiNAS into $TARGET"
if [ -d "$TARGET/.git" ]; then
    say "found an existing checkout — updating"
    git -C "$TARGET" fetch origin
    # detach any local edits from the ref we're about to pull, then fast-forward
    git -C "$TARGET" checkout "$REF" || {
        warn "could not check out '$REF'; leaving working tree untouched"
        exit 1
    }
    git -C "$TARGET" pull --ff-only origin "$REF"
    ok "up to date"
elif [ -e "$TARGET" ]; then
    printf "%s already exists and is not a git checkout. Move it aside or set PINAS_DIR.\n" "$TARGET" >&2
    exit 1
else
    mkdir -p "$(dirname "$TARGET")"
    git clone --branch "$REF" --depth 1 "$REPO_URL" "$TARGET"
    ok "cloned"
fi

# ------------------------------------------------------------
log "Running setup"
cd "$TARGET"
# hand any positional args + inherited SETUP_* env vars to setup.sh
exec ./setup.sh "$@"
