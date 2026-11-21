#!/usr/bin/env bash
# Build the UI if it is missing or stale, then start the server.
# Extra arguments go to sessions.py, e.g. ./start.sh --port 9000 --no-llm
set -euo pipefail
cd "$(dirname "$0")"

# npm rewrites node_modules/.package-lock.json on every install, so it marks the last one.
stamp=web/node_modules/.package-lock.json
if [ ! -f "$stamp" ] || [ -n "$(find web/package.json web/package-lock.json -newer "$stamp" -print -quit)" ]; then
  (cd web && npm install)
fi
if [ ! -f web/dist/index.html ] ||
   [ -n "$(find web/src web/index.html web/package.json web/package-lock.json web/tsconfig.json web/vite.config.ts \
             -newer web/dist/index.html -print -quit)" ]; then
  (cd web && npm run build)
fi

exec uv run sessions.py "$@"
