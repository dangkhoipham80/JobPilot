#!/usr/bin/env bash
# Wait for the launchd-managed API to answer, and make sure it is *that* process
# answering. Shared by install.sh and update.sh.
#
# Two ways a plain `curl /health` lies:
# - launchctl bootstrap/kickstart return as soon as the process is spawned, so
#   they "succeed" even when the app dies during startup — which is exactly what
#   the token guard does on a bad .env.
# - This checkout is also the dev checkout. A `uvicorn --reload` left running on
#   :8000 answers /health with 200 while the agent fails to bind and restarts
#   every 10s — and the dashboard behind tailscale serve is then talking to the
#   dev server, with its second task queue.

set -uo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
label=com.jobpilot.api

for i in $(seq 1 30); do
    agent_pid="$(launchctl list | awk -v l="$label" '$3 == l { print $1 }')"
    listen_pid="$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null | head -1)"
    # Agent pid may read "-" here: it is crash-looping on the bind.
    if [ -n "$listen_pid" ] && [ "$listen_pid" != "$agent_pid" ]; then
        echo "port 8000 is held by pid $listen_pid, not the $label agent (pid $agent_pid):" >&2
        ps -o pid=,command= -p "$listen_pid" >&2
        echo "stop that process (a dev server?) and run this again" >&2
        exit 1
    fi
    if [ "$listen_pid" = "$agent_pid" ] \
        && curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "API healthy after ${i}s (pid $agent_pid) — logs in $repo/logs/"
        exit 0
    fi
    sleep 1
done
echo "API did not come up within 30s — tail of logs/api.log:" >&2
tail -n 40 "$repo/logs/api.log" >&2 || true
exit 1
