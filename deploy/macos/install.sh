#!/usr/bin/env bash
# Install (or reinstall) the JobPilot launchd agents for the current user.
#
#   com.jobpilot.api     at login, kept alive — restarted if it dies
#   com.jobpilot.crawl   08:30 and 18:30
#   com.jobpilot.backup  at login and 03:00
#
# LaunchAgents, not LaunchDaemons, on purpose: they start when you log in and
# stop when you shut down, which is exactly the lifetime asked for ("on when the
# Mac is on"). With FileVault on, the boot-time unlock *is* the login, so a
# power-on followed by the password brings everything up. Postgres (brew
# services) and Tailscale already live at this level, so a daemon would only
# start before the things it depends on.
#
# Backup also runs at login because the 03:00 slot never fires on a Mac that is
# shut down overnight; launchd catches up a missed slot after *sleep*, not after
# power-off. keep_last in config.yaml caps the pile-up from frequent reboots.
#
# Re-running is safe: each agent is booted out and loaded again.
#
#     ./deploy/macos/install.sh            # install + (re)start
#     ./deploy/macos/install.sh --uninstall

set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
agents="$HOME/Library/LaunchAgents"
domain="gui/$(id -u)"
labels=(com.jobpilot.api com.jobpilot.crawl com.jobpilot.backup)

for label in "${labels[@]}"; do
    launchctl bootout "$domain/$label" 2>/dev/null || true
    # bootout returns before the job is fully torn down (slower still while it
    # is mid crash-loop), and bootstrapping the same label in that window fails
    # with a bare "5: Input/output error".
    for _ in $(seq 1 20); do
        launchctl print "$domain/$label" >/dev/null 2>&1 || break
        sleep 0.5
    done
    rm -f "$agents/$label.plist"
done
if [ "${1:-}" = "--uninstall" ]; then
    echo "removed: ${labels[*]}"
    exit 0
fi

# Fail here, not at 08:30 tomorrow.
[ -x "$repo/.venv/bin/python" ] || { echo "no .venv in $repo — run 'make install-all' first" >&2; exit 1; }
[ -f "$repo/.env" ] || { echo "no .env in $repo — copy .env.example and fill it in" >&2; exit 1; }
[ -f "$repo/web/dist/index.html" ] || echo "warning: web/dist missing — run deploy/macos/update.sh to build the dashboard" >&2
chmod +x "$repo/deploy/macos/run.sh"
mkdir -p "$agents" "$repo/logs"

# $1 label, $2 job, $3 extra plist keys
write_plist() {
    cat >"$agents/$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$1</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$repo/deploy/macos/run.sh</string>
        <string>$2</string>
    </array>
    <key>WorkingDirectory</key><string>$repo</string>
    <!-- Output the wrapper itself cannot catch (e.g. bash failing to start). -->
    <key>StandardOutPath</key><string>$repo/logs/launchd.log</string>
    <key>StandardErrorPath</key><string>$repo/logs/launchd.log</string>
$3
</dict>
</plist>
EOF
    plutil -lint -s "$agents/$1.plist"
}

write_plist com.jobpilot.api api '
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>10</integer>'

write_plist com.jobpilot.crawl crawl '
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>LowPriorityIO</key><true/>'

write_plist com.jobpilot.backup backup '
    <key>RunAtLoad</key><true/>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
    <key>LowPriorityIO</key><true/>'

for label in "${labels[@]}"; do
    launchctl bootstrap "$domain" "$agents/$label.plist"
    echo "  loaded: $label"
done

"$repo/deploy/macos/healthcheck.sh"
