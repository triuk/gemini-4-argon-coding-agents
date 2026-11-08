#!/bin/sh
set -eu
D=$(CDPATH= cd "$(dirname "$0")" && pwd)
PORT=${ARGON_PORT:-}
[ -n "$PORT" ] || { if [ -s "$D/proxy-port" ]; then PORT=$(cat "$D/proxy-port"); else PORT=4000; fi; }
case "$PORT" in ''|*[!0-9]*) echo 'ARGON_PORT must be an integer from 1 to 65535.' >&2; exit 2 ;; esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || { echo 'Invalid ARGON_PORT.' >&2; exit 2; }
[ -s "$D/vertex-project" ] || { echo 'Missing project; run setup.sh first.' >&2; exit 1; }
[ -x "$D/.venv/bin/litellm" ] || { echo 'Missing LiteLLM; run setup.sh without --files-only.' >&2; exit 1; }
export VERTEXAI_PROJECT="$(cat "$D/vertex-project")"
export VERTEXAI_LOCATION=global
export PYTHONPATH="$D${PYTHONPATH:+:$PYTHONPATH}"
export LITELLM_TELEMETRY=False
export LITELLM_LOCAL_MODEL_COST_MAP=True
exec "$D/.venv/bin/litellm" --config "$D/argon.yaml" --host 127.0.0.1 --port "$PORT"
