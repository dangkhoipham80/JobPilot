#!/usr/bin/env bash
# Pull the current main onto the host and restart. Idempotent: safe to re-run.
#
# Lives in the repo rather than in the CI workflow so that deploying by hand and
# deploying from GitHub run the same steps. A deploy path that only exists in
# YAML is one you cannot test from the box it deploys to.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/jobpilot}"
cd "$APP_DIR"

echo "==> fetching"
git fetch --prune origin
git checkout main
git reset --hard origin/main

echo "==> python deps"
.venv/bin/pip install --quiet -e '.[all]'

echo "==> migrations"
# Before the restart, not after: the new code may expect columns the old schema
# does not have, and a service that boots against a stale schema fails in
# whichever request touches the new column first — long after the deploy is
# reported green.
.venv/bin/alembic upgrade head

echo "==> dashboard"
# The token is compiled into the bundle by Vite, so the bundle must be rebuilt on
# the host that holds the real token — a bundle built in CI carries CI's
# placeholder. Deriving VITE_API_TOKEN from JOBPILOT_API_TOKEN here means there
# is exactly one place the token is written; a separate web/.env.local on the
# server is a second copy waiting to drift out of sync and produce a dashboard
# that 401s against its own backend.
set -a
# shellcheck disable=SC1091
source .env
set +a
export VITE_API_TOKEN="$JOBPILOT_API_TOKEN"

cd web
npm ci --silent
npm run build
cd ..

echo "==> restart"
sudo systemctl restart jobpilot-api

# Prove it came back rather than assuming. `systemctl restart` returns as soon
# as the process is spawned, so it succeeds even when the app dies during
# startup — which is exactly what the token guard does on a bad .env.
echo "==> health check"
for i in $(seq 1 20); do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null; then
        echo "healthy after ${i}s"
        curl -fsS http://127.0.0.1:8000/health
        exit 0
    fi
    sleep 1
done

echo "service did not answer /health within 20s — recent log:" >&2
sudo journalctl -u jobpilot-api -n 40 --no-pager >&2
exit 1
