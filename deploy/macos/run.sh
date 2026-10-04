#!/usr/bin/env bash
# Entry point for the three JobPilot launchd agents:  run.sh api|crawl|backup
#
# Why a wrapper instead of pointing the plist straight at python:
#
# 1. PATH. launchd starts agents with PATH=/usr/bin:/bin:/usr/sbin:/sbin. Every
#    tool JobPilot shells out to lives under Homebrew: tectonic (PDF builds) in
#    /opt/homebrew/bin, and pg_dump in the *keg-only* postgresql@NN formula,
#    which is never linked into bin at all. Without this, the API comes up fine
#    and then the first PDF build "has no LaTeX engine" and the nightly backup
#    "has no pg_dump" — on a machine where both work from a terminal.
#
# 2. LOGS. A launchd job that dies leaves an exit code in `launchctl print` and
#    nothing else. Each job appends to logs/<job>.log here.
#
# 3. POSTGRES AT LOGIN. Postgres is itself a LaunchAgent (brew services), started
#    in the same login burst as these. Waiting for it here turns a race into a
#    few seconds of delay instead of a crash, a throttled restart and a
#    traceback in the log on every boot.

set -uo pipefail

job="${1:?usage: run.sh api|crawl|backup}"

# Repo root is two levels up from this file, whatever the checkout is called.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs
log="logs/$job.log"

# Keep each log bounded: one rotation at 5 MB is plenty for a personal box.
if [ -f "$log" ] && [ "$(stat -f%z "$log")" -gt 5242880 ]; then
    mv -f "$log" "$log.1"
fi

# postgresql@NN kegs go *before* /opt/homebrew/bin: whatever happens to be
# linked into bin may be an older major than the server, and pg_dump refuses to
# dump a newer server. The sort leaves the newest keg first on PATH.
kegs=""
for kegbin in $(ls -d /opt/homebrew/opt/postgresql@*/bin /usr/local/opt/postgresql@*/bin 2>/dev/null | sort -t@ -k2 -n -r); do
    kegs="$kegs$kegbin:"
done
export PATH="$kegs/opt/homebrew/bin:/usr/local/bin:$PATH"

py=.venv/bin/python
# Redirected to a file, Python block-buffers stdout: a crawl that has been
# working for ten minutes shows an empty log, indistinguishable from a hang.
export PYTHONUNBUFFERED=1
{
    echo
    echo "============ $job started $(date '+%F %T') ============"
} >>"$log"

# Wait up to 60s for Postgres on 127.0.0.1:5432, where brew services puts it
# and where DATABASE_URL points.
if command -v pg_isready >/dev/null; then
    for _ in $(seq 1 30); do
        pg_isready -q -h 127.0.0.1 && break
        sleep 2
    done
fi

case "$job" in
    api)
        # --workers 1 is mandatory, not tuning: the task queue is a
        # ThreadPoolExecutor inside this process, so a second worker is a second
        # queue with its own WebSocket manager. No --reload for the same reason.
        # Bound to loopback; other devices reach it only via `tailscale serve`.
        # exec so launchd's KeepAlive watches uvicorn itself, not this shell.
        exec "$py" -m uvicorn jobpilot.api.main:app \
            --host 127.0.0.1 --port 8000 --workers 1 >>"$log" 2>&1
        ;;
    crawl)
        # Hard limit, like TimeoutStartSec on the VPS and ExecutionTimeLimit on
        # Windows. launchd has no such key, and it never starts a second copy of
        # a job that is still running — so a crawl hung in Chromium on a
        # challenge page would silently swallow every later slot until reboot,
        # while `launchctl list` shows a PID that looks like healthy work.
        # macOS has no GNU `timeout`, hence the watchdog by hand. Killing a
        # crawl mid-run is safe: persist is idempotent.
        "$py" -m jobpilot.cli crawl >>"$log" 2>&1 &
        child=$!
        ( sleep 2700 && kill -0 "$child" 2>/dev/null \
            && echo "crawl exceeded 45 min — killing pid $child" >>"$log" \
            && kill "$child" ) &
        watchdog=$!
        wait "$child"
        rc=$?
        pkill -P "$watchdog" 2>/dev/null; kill "$watchdog" 2>/dev/null
        echo "============ $job exited $(date '+%F %T') rc=$rc ============" >>"$log"
        exit $rc
        ;;
    backup)
        # Destination and retention come from `backup:` in config.yaml, so this,
        # the CLI and the dashboard button all apply the same rules.
        "$py" -m jobpilot.cli backup --verbose >>"$log" 2>&1
        ;;
    *)
        echo "unknown job: $job" >>"$log"
        exit 2
        ;;
esac
rc=$?
echo "============ $job exited $(date '+%F %T') rc=$rc ============" >>"$log"
exit $rc
