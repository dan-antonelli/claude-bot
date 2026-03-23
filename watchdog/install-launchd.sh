#!/bin/bash
# Install the watchdog as a launchd service so macOS keeps it alive permanently.
# On crash or logout/login, launchd restarts it automatically.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(which python3)"
PLIST="$HOME/Library/LaunchAgents/com.claude-bot.watchdog.plist"

# Stop tmux session if running — launchd takes over
tmux kill-session -t claude-watchdog 2>/dev/null && echo "Stopped tmux session." || true

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.claude-bot.watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$REPO/watchdog/watchdog.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO</string>
  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/claude-watchdog.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/claude-watchdog.log</string>
</dict>
</plist>
PLIST_EOF

launchctl load "$PLIST"
echo "Watchdog installed as launchd service (com.claude-bot.watchdog)."
echo "Logs: tail -f /tmp/claude-watchdog.log"
echo "Uninstall: launchctl unload $PLIST && rm $PLIST"
