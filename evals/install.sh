#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES="${QUINOVO_EVAL_TEMPLATES:-$HOME/projects/quinovo-eval-templates}"
if [[ ! -f "$TEMPLATES/scripts/install.py" ]]; then
  echo "missing $TEMPLATES/scripts/install.py" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. "$ROOT/.env"
set +a
export EVAL_PUBLIC_KEY="${EVAL_PUBLIC_KEY:-$LANGFUSE_PUBLIC_KEY}"
export EVAL_SECRET_KEY="${EVAL_SECRET_KEY:-$LANGFUSE_SECRET_KEY}"
export EVAL_BASE_URL="${EVAL_BASE_URL:-${LANGFUSE_BASE_URL:-http://localhost:3000}}"
export EVAL_PROVIDER="${EVAL_PROVIDER:-MiniMax}"
export EVAL_MODEL="${EVAL_MODEL:-MiniMax-M3}"
export EVAL_NAME_PREFIX="${EVAL_NAME_PREFIX:-quinovo/}"
python3 "$TEMPLATES/scripts/install.py" --rule --tag quinovo "$@"
python3 "$ROOT/evals/install_dataset.py" --collect
