#!/usr/bin/env bash
# Rebuild and restart JobPilot on the Mac from the CURRENT checkout.
#
# Unlike deploy/update.sh (VPS), this does not fetch or `git reset --hard`: on
# the Mac the deploy checkout is also the one being edited, and a deploy script
# that silently throws away uncommitted work is a worse failure than a stale
# deploy. Pull yourself first if you want the latest main.

set -euo pipefail

cd "$(dirname "$0")/../.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "==> python deps"
.venv/bin/python -m pip install --quiet -e '.[all]'

echo "==> migrations"
# Before the restart: new code may expect columns the old schema lacks.
.venv/bin/python -m alembic upgrade head

echo "==> dashboard"
# The token is compiled into the bundle, so derive it from .env here — one place
# the token is written, instead of a web/.env.local copy waiting to drift into a
# dashboard that 401s against its own backend.
#
# Read through the backend's own settings loader, not grep|cut: a quoted value
# (JOBPILOT_API_TOKEN="abc") is valid .env, and cut would bake the quotes into
# the bundle — every /api call 401s while /health, which needs no token, still
# reports the deploy healthy.
VITE_API_TOKEN="$(.venv/bin/python -c 'from jobpilot.config import get_secrets; print(get_secrets().jobpilot_api_token)')"
if [ -z "$VITE_API_TOKEN" ] || [ "$VITE_API_TOKEN" = "changeme" ]; then
    echo "JOBPILOT_API_TOKEN is missing from .env — see DEPLOY.md §2" >&2
    exit 1
fi
export VITE_API_TOKEN
(cd web && npm ci --silent && npm run build)

echo "==> restart"
agent="gui/$(id -u)/com.jobpilot.api"
if ! launchctl print "$agent" >/dev/null 2>&1; then
    echo "agent not installed yet — run deploy/macos/install.sh"
    exit 0
fi
launchctl kickstart -k "$agent"

"$(dirname "$0")/healthcheck.sh"
