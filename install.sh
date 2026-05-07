#!/usr/bin/env bash
# =============================================================================
# agent-mcp — installation script for Linux and macOS
# =============================================================================
#
# Usage:
#   bash install.sh [OPTIONS]
#
# Options:
#   --no-venv         Skip virtual environment creation (use current Python)
#   --venv-dir DIR    Path for the virtual environment  (default: .venv)
#   --data-dir DIR    Override the platform data directory
#   --no-frontend     Skip Node.js/pnpm frontend dependency check
#   --dev             Install in editable mode (pip install -e .)
#   --help            Show this help
#
# =============================================================================
set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
if [ -t 1 ] && command -v tput &>/dev/null && tput colors &>/dev/null; then
    _BOLD=$(tput bold)
    _RED=$(tput setaf 1)
    _GRN=$(tput setaf 2)
    _YLW=$(tput setaf 3)
    _CYN=$(tput setaf 6)
    _RST=$(tput sgr0)
else
    _BOLD="" _RED="" _GRN="" _YLW="" _CYN="" _RST=""
fi

info()    { echo "${_CYN}  ●${_RST} $*"; }
success() { echo "${_GRN}  ✔${_RST} $*"; }
warn()    { echo "${_YLW}  ⚠${_RST} $*"; }
error()   { echo "${_RED}  ✖${_RST} $*" >&2; }
header()  { echo; echo "${_BOLD}${_CYN}══ $* ══${_RST}"; echo; }
die()     { error "$*"; exit 1; }

# ── defaults ──────────────────────────────────────────────────────────────────
USE_VENV=true
VENV_DIR=".venv"
DATA_DIR_OVERRIDE=""
SKIP_FRONTEND=false
EDITABLE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-venv)       USE_VENV=false ;;
        --venv-dir)      VENV_DIR="$2"; shift ;;
        --data-dir)      DATA_DIR_OVERRIDE="$2"; shift ;;
        --no-frontend)   SKIP_FRONTEND=true ;;
        --dev)           EDITABLE=true ;;
        --help)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) die "Unknown option: $1. Run with --help for usage." ;;
    esac
    shift
done

# ── banner ────────────────────────────────────────────────────────────────────
echo
echo "${_BOLD}${_CYN}  ╔══════════════════════════════════════╗"
echo "  ║         agent-mcp  installer         ║"
echo "  ╚══════════════════════════════════════╝${_RST}"
echo

# ── Python check ─────────────────────────────────────────────────────────────
header "Checking Python"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major="${ver%%.*}"
        minor="${ver#*.}"
        if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

[[ -z "$PYTHON" ]] && die "Python 3.11 or newer is required but was not found.\n  Install it from https://python.org/downloads or via your package manager."

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
success "Python $PY_VERSION  ($PYTHON)"

# ── virtual environment ───────────────────────────────────────────────────────
header "Virtual environment"

cd "$SCRIPT_DIR"

if $USE_VENV; then
    if [[ -d "$VENV_DIR" ]]; then
        info "Existing virtual environment found at $VENV_DIR"
    else
        info "Creating virtual environment at $VENV_DIR"
        "$PYTHON" -m venv "$VENV_DIR"
    fi

    # Activate
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
    success "Virtual environment ready"
else
    warn "--no-venv: using system/current Python ($PYTHON)"
fi

# ── pip upgrade ───────────────────────────────────────────────────────────────
info "Upgrading pip…"
"$PYTHON" -m pip install --quiet --upgrade pip

# ── package install ───────────────────────────────────────────────────────────
header "Installing agent-mcp"

if $EDITABLE; then
    info "Installing in editable/development mode…"
    "$PYTHON" -m pip install -e ".[graph-watch]"
else
    info "Installing package…"
    "$PYTHON" -m pip install ".[graph-watch]"
fi
success "Package installed"

# ── data directory setup ──────────────────────────────────────────────────────
header "Setting up data directory"

DATA_DIR=$("$PYTHON" - <<'PYEOF'
import os, sys
from pathlib import Path
override = os.environ.get("AGENT_DATA_DIR", "")
if override:
    print(Path(override).expanduser().resolve()); sys.exit()
if sys.platform == "darwin":
    print(Path.home() / "Library" / "Application Support" / "agent-mcp")
else:
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg).expanduser() if xdg else (Path.home() / ".local" / "share")
    print(base / "agent-mcp")
PYEOF
)

# Allow CLI override to propagate
[[ -n "$DATA_DIR_OVERRIDE" ]] && DATA_DIR="$DATA_DIR_OVERRIDE"

info "Data directory: $DATA_DIR"
mkdir -p \
    "$DATA_DIR/logs" \
    "$DATA_DIR/traces" \
    "$DATA_DIR/workspaces" \
    "$DATA_DIR/checkpoints"
success "Data directory created"

# ── .env configuration ────────────────────────────────────────────────────────
header "Configuration"

ENV_FILE="$DATA_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    info ".env already exists — skipping (delete $ENV_FILE to regenerate)"
else
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    # Strip comment lines that start with just '#' to keep the file clean
    success ".env written to $ENV_FILE"
    echo
    warn "Review and edit ${_BOLD}$ENV_FILE${_RST} before starting the server."
    echo "  Key settings to configure:"
    echo "    AGENT_API_LLM_PROVIDER   (ollama | openai | anthropic)"
    echo "    AGENT_API_OPENAI_API_KEY (if using OpenAI)"
    echo "    AGENT_API_DEFAULT_MODEL"
fi

# ── Ollama detection ──────────────────────────────────────────────────────────
header "Checking Ollama"

if command -v ollama &>/dev/null; then
    OLLAMA_VER=$(ollama --version 2>/dev/null || echo "unknown")
    success "Ollama found: $OLLAMA_VER"

    if ! curl -sf http://127.0.0.1:11434/api/tags &>/dev/null; then
        warn "Ollama daemon is not running. Start it with:  ollama serve"
    else
        success "Ollama daemon is reachable at http://127.0.0.1:11434"
        DEFAULT_MODEL=$(grep -E '^AGENT_API_DEFAULT_MODEL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "qwen2.5-coder:7b")
        if ! ollama list 2>/dev/null | grep -q "${DEFAULT_MODEL%%:*}"; then
            echo
            warn "Default model '${_BOLD}$DEFAULT_MODEL${_RST}' not found locally."
            echo "  Pull it with:  ollama pull $DEFAULT_MODEL"
        else
            success "Default model '$DEFAULT_MODEL' is available"
        fi
    fi
else
    warn "Ollama not found in PATH."
    echo "  → Install from https://ollama.com  or use OpenAI/Anthropic instead."
    echo "    Then pull a model:  ollama pull qwen2.5-coder:7b"
fi

# ── Node.js / frontend (optional) ─────────────────────────────────────────────
if ! $SKIP_FRONTEND; then
    header "Checking frontend dependencies (optional)"
    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    if [[ -d "$FRONTEND_DIR" ]]; then
        if command -v node &>/dev/null; then
            NODE_VER=$(node --version)
            success "Node.js $NODE_VER"
            if command -v pnpm &>/dev/null; then
                info "Installing frontend dependencies…"
                (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile 2>&1 | tail -5)
                success "Frontend dependencies installed"
                info "Build the frontend:  cd frontend && pnpm build"
            elif command -v npm &>/dev/null; then
                warn "pnpm not found — using npm."
                (cd "$FRONTEND_DIR" && npm install 2>&1 | tail -5)
                success "Frontend dependencies installed (npm)"
            else
                warn "No package manager (pnpm/npm) found — skipping frontend."
            fi
        else
            warn "Node.js not found — frontend skipped. Install from https://nodejs.org"
        fi
    else
        info "No frontend directory found — skipping."
    fi
fi

# ── locate entry-point scripts ────────────────────────────────────────────────
if $USE_VENV; then
    BIN="$VENV_DIR/bin"
else
    BIN=$(dirname "$(command -v python3)")
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo
echo "${_BOLD}${_GRN}  ════════════════════════════════════════"
echo "   agent-mcp installation complete! 🎉"
echo "  ════════════════════════════════════════${_RST}"
echo
echo "  Data directory : ${_BOLD}$DATA_DIR${_RST}"
echo "  Config file    : ${_BOLD}$ENV_FILE${_RST}"
echo "  Database       : ${_BOLD}$DATA_DIR/agent.db${_RST}"
echo "  Logs           : ${_BOLD}$DATA_DIR/logs/agent.log${_RST}"
echo
echo "${_BOLD}  Next steps:${_RST}"
if $USE_VENV; then
    echo "  1. Activate the environment:"
    echo "       ${_CYN}source $VENV_DIR/bin/activate${_RST}"
else
    echo "  1. (No venv — commands available on PATH)"
fi
echo "  2. Start the API server:"
echo "       ${_CYN}agent-api${_RST}"
echo "  3. Open a new terminal and start the interactive shell:"
echo "       ${_CYN}agent${_RST}"
echo
echo "  Documentation  : ${_CYN}README.md${_RST}"
echo
