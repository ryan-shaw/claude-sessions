#!/usr/bin/env bash
# Build the UI if it is missing or stale, then start the server.
# Extra arguments go to sessions.py, e.g. ./start.sh --port 9000 --no-llm
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d web/node_modules ]; then
  (cd web && npm install)
fi
if [ ! -f web/dist/index.html ] ||
   [ -n "$(find web/src web/index.html web/package.json web/vite.config.ts -newer web/dist/index.html -print -quit)" ]; then
  (cd web && npm run build)
fi

exec uv run sessions.py "$@"
