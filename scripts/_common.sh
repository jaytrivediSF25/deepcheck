#!/usr/bin/env bash
# Shared setup for the quickstart scripts. Sourced, not executed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

find_python() {
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  echo "deepcheck needs Python 3.10 or newer on PATH." >&2
  return 1
}

setup_env() {
  bold "1/4  Python environment"
  PY="$(find_python)"
  ok "$("$PY" --version 2>&1)"

  if [ ! -d .venv ]; then
    "$PY" -m venv .venv
    ok "created .venv"
  else
    ok ".venv already present"
  fi

  # Windows layout (Git Bash) puts binaries in Scripts/, POSIX in bin/.
  if [ -f .venv/Scripts/python.exe ]; then
    VENV_PY=".venv/Scripts/python.exe"
  else
    VENV_PY=".venv/bin/python"
  fi

  bold "2/4  Dependencies"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -e .
  ok "deepcheck installed (editable)"

  bold "3/4  Upstream transcriber"
  if [ -d vendor/youtube-deepsummary/.git ]; then
    ok "youtube-deepsummary already vendored"
  else
    git clone --depth 1 https://github.com/nickita-khylkouski/youtube-deepsummary.git \
      vendor/youtube-deepsummary >/dev/null 2>&1
    ok "cloned youtube-deepsummary"
  fi
  "$VENV_PY" -m pip install --quiet "youtube-transcript-api<1.2"
  ok "transcript backend ready"
}

check_credentials() {
  bold "4/4  Credentials"
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    ok "ANTHROPIC_API_KEY is set"
  elif [ -f .env ] && grep -q '^ANTHROPIC_API_KEY=.\+' .env 2>/dev/null; then
    ok "ANTHROPIC_API_KEY found in .env"
  elif command -v ant >/dev/null 2>&1 && ant auth status >/dev/null 2>&1; then
    ok "authenticated via an ant profile"
  else
    warn "no Anthropic credential found"
    dim "     export ANTHROPIC_API_KEY=sk-ant-...   (or run: ant auth login)"
    dim "     'deepcheck transcribe' works without one."
  fi
}

launch() {
  local agent="$1" install_hint="$2" prompt="$3"
  echo
  if ! command -v "$agent" >/dev/null 2>&1; then
    warn "'$agent' is not on PATH"
    dim "     install it with: $install_hint"
    dim "     Setup is done — rerun this script once $agent is installed."
    exit 0
  fi
  bold "Opening $agent in $(pwd)"
  echo
  exec "$agent" "$prompt"
}
