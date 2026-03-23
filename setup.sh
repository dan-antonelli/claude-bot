#!/bin/bash
# Full setup: install deps, start watchdog + bot, self-test.
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
step() { echo -e "${YELLOW}→${NC} $1"; }

echo "━━━ claude-bot setup ━━━"
echo

# 1. Check .env
step "Checking .env..."
[ -f "$REPO/.env" ] || fail ".env not found — copy .env.example and fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
for var in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
    grep -q "^${var}=" "$REPO/.env" || fail "$var not set in .env"
done
ok ".env OK"

# 2. Install Python dependencies
step "Installing Python dependencies..."
pip3 install -q python-telegram-bot python-dotenv pytest pytest-asyncio
ok "Dependencies installed"

# 3. Install watchdog as launchd service (starts watchdog + bot automatically)
step "Installing watchdog as launchd service..."
"$REPO/watchdog/install-launchd.sh"
ok "Watchdog service installed"

# 4. Wait for watchdog
step "Waiting for watchdog..."
for i in $(seq 1 10); do
    if launchctl list | grep -q "com.claude-bot.watchdog"; then
        ok "Watchdog running"
        break
    fi
    [ "$i" -eq 10 ] && fail "Watchdog did not start within 10s — check: tail -f /tmp/claude-watchdog.log"
    sleep 1
done

# 5. Wait for bot (watchdog auto-starts it)
step "Waiting for bot..."
for i in $(seq 1 20); do
    if tmux has-session -t claude-bot 2>/dev/null; then
        ok "Bot running"
        break
    fi
    [ "$i" -eq 20 ] && fail "Bot did not start within 20s — check: tail -f /tmp/claude-watchdog.log"
    sleep 1
done

# 6. Run test suite
step "Running self-tests..."
cd "$REPO"
if pytest -q; then
    ok "All tests passed"
else
    fail "Tests failed — check output above"
fi

echo
echo "━━━ Setup complete ━━━"
echo "  Watchdog logs:  tail -f /tmp/claude-watchdog.log"
echo "  Bot session:    tmux attach -t claude-bot"
echo "  Control:        echo restart > /tmp/claude-bot.fifo"
