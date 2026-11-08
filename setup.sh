#!/usr/bin/env bash
# Install the ADC-backed proxy and a separate codex-argon command.
set -euo pipefail

FILES_ONLY=0
T3=0
T3_SETTINGS="${T3CODE_HOME:-$HOME/.t3}/userdata/settings.json"
T3_INSTANCE=codex_argon_proxy
CODEX_SHARED_HOME=
PORT="${ARGON_PORT:-}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --files-only) FILES_ONLY=1; shift ;;
    --t3) T3=1; shift ;;
    --t3-settings|--t3-instance|--codex-home|--port)
      [ "$#" -ge 2 ] || { printf 'Missing value for %s\n' "$1" >&2; exit 2; }
      case "$1" in
        --t3-settings) T3_SETTINGS="$2" ;;
        --t3-instance) T3_INSTANCE="$2" ;;
        --codex-home) CODEX_SHARED_HOME="$2" ;;
        --port) PORT="$2" ;;
      esac
      shift 2 ;;
    -h|--help)
      printf '%s\n' 'Usage: VERTEX_PROJECT=your-project-id ./setup.sh [options]' \
        'Installs into ~/.config/argon-codex and ~/.local/bin; keeps Codex config intact.' \
        '--t3                 Add/update a separate Argon instance in T3, including effort.' \
        '--t3-settings PATH   T3 server settings file (default: ~/.t3/userdata/settings.json).' \
        '--t3-instance ID     Instance ID (default: codex_argon_proxy).' \
        '--codex-home PATH    Shared CODEX_HOME for T3 thread continuation.' \
        '--port NUMBER        Proxy port; saved for both the proxy and Codex launcher.' \
        '--files-only         Skip dependencies, proxy startup and live tests.'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${ARGON_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/argon-codex}"
BIN="${ARGON_BIN_DIR:-$HOME/.local/bin}"
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [ -z "$PORT" ] && [ -s "$CFG/proxy-port" ]; then PORT="$(cat "$CFG/proxy-port")"; fi
PORT="${PORT:-4000}"
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$PORT" -le 65535 ] || die 'Invalid proxy port (1–65535).'
PYTHON=
if [ "$T3" = 1 ]; then
  # Files-only mode has no venv; use a host Python solely for the JSON merge.
  PYTHON="$(command -v python3 || true)"
  [ -n "$PYTHON" ] || [ "$FILES_ONLY" = 0 ] || die '--t3 --files-only needs python3.'
  if [ -n "$PYTHON" ]; then
    "$PYTHON" "$REPO_DIR/scripts/configure_t3.py" --settings "$T3_SETTINGS" \
      --instance "$T3_INSTANCE" --launcher "$BIN/codex-argon" --check
  fi
fi

VERTEX_PROJECT="${VERTEX_PROJECT:-}"
if [ -z "$VERTEX_PROJECT" ] && [ -s "$CFG/vertex-project" ]; then
  VERTEX_PROJECT="$(cat "$CFG/vertex-project")"
fi
[[ "$VERTEX_PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] \
  || die 'Set VERTEX_PROJECT to a Google Cloud project ID (6–30 lowercase letters, digits or hyphens).'

if [ "$FILES_ONLY" = 0 ]; then
  command -v uv >/dev/null 2>&1 || die 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
fi
mkdir -p "$CFG" "$BIN"
chmod 700 "$CFG"

if [ "$FILES_ONLY" = 0 ]; then
  if [ ! -x "$CFG/.venv/bin/python" ]; then
    uv venv --python 3.12 "$CFG/.venv"
  fi
  uv pip install --python "$CFG/.venv/bin/python" -r "$REPO_DIR/requirements.txt"
  PYTHON="$CFG/.venv/bin/python"
fi

copy_file() {
  local source="$1" target="$2"
  if [ -f "$target" ]; then
    cmp -s "$source" "$target" && return 0
    cp -p "$target" "$target.bak-$STAMP"
    printf 'Backup: %s\n' "$target.bak-$STAMP"
  fi
  cp "$source" "$target"
}
copy_file "$REPO_DIR/proxy/argon.yaml" "$CFG/argon.yaml"
copy_file "$REPO_DIR/proxy/argon_hooks.py" "$CFG/argon_hooks.py"
copy_file "$REPO_DIR/proxy/start-argon.sh" "$CFG/start-argon.sh"
copy_file "$REPO_DIR/codex/codex-argon" "$BIN/codex-argon"
write_value() {
  local target="$1" value="$2"
  if [ -f "$target" ]; then
    [ "$(cat "$target")" = "$value" ] && return 0
    cp -p "$target" "$target.bak-$STAMP"
    printf 'Backup: %s\n' "$target.bak-$STAMP"
  fi
  printf '%s\n' "$value" > "$target"
}
write_value "$CFG/vertex-project" "$VERTEX_PROJECT"
write_value "$CFG/proxy-port" "$PORT"
chmod +x "$CFG/start-argon.sh" "$BIN/codex-argon"

if [ "$T3" = 1 ]; then
  T3_ARGS=(--settings "$T3_SETTINGS" --instance "$T3_INSTANCE" --launcher "$BIN/codex-argon")
  [ -z "$CODEX_SHARED_HOME" ] || T3_ARGS+=(--codex-home "$CODEX_SHARED_HOME")
  "$PYTHON" "$REPO_DIR/scripts/configure_t3.py" "${T3_ARGS[@]}"
fi

printf '\nInstalled. Start the proxy in a terminal:\n  %s\nThen run in another terminal:\n  %s\n' \
  "$CFG/start-argon.sh" "$BIN/codex-argon"
if [ "$FILES_ONLY" = 1 ]; then
  printf 'Dependencies skipped (--files-only). Run setup without this flag before starting.\n'
fi
