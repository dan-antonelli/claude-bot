#!/usr/bin/env python3
"""Watchdog for claude-bot: restarts the bot independently of the bot process."""

import json
import logging
import os
import select
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID      = int(os.environ["TELEGRAM_CHAT_ID"])
PIPE_PATH    = Path(os.environ.get("WATCHDOG_PIPE", "/tmp/claude-bot.fifo"))
BOT_SESSION  = "claude-bot"
START_SCRIPT = Path(__file__).parent.parent / "start-bot.sh"

log = logging.getLogger(__name__)

_intentionally_stopped = False  # guard against health-check auto-restart during manual stop
_update_offset = 0              # Telegram getUpdates offset; tracks next unseen update


# ── Core helpers ──────────────────────────────────────────────────────────────

def send_telegram(text: str) -> None:
    """POST a message to Telegram; swallows all errors."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req):
            pass
    except Exception:
        pass


def get_updates() -> list:
    """Fetch pending Telegram updates, advancing _update_offset. Returns list of updates."""
    global _update_offset
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={_update_offset}&timeout=0"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        updates = data.get("result", [])
        if updates:
            _update_offset = updates[-1]["update_id"] + 1
        return updates
    except Exception:
        return []


def drain_updates() -> None:
    """Consume all pending updates without replying (call when bot stops to skip old messages)."""
    get_updates()


def bot_is_running() -> bool:
    """Return True if the claude-bot tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", BOT_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


def kill_bot() -> None:
    """Kill the claude-bot tmux session."""
    subprocess.run(
        ["tmux", "kill-session", "-t", BOT_SESSION],
        capture_output=True,
    )


def start_bot() -> bool:
    """Run start-bot.sh and poll until the bot is running (up to 3 s)."""
    subprocess.run(["bash", str(START_SCRIPT)], capture_output=True)
    deadline = time.time() + 3
    while time.time() < deadline:
        if bot_is_running():
            return True
        time.sleep(0.2)
    return False


# ── Command handlers ──────────────────────────────────────────────────────────

def handle_restart() -> None:
    send_telegram("🔄 Restarting bot...")
    kill_bot()
    success = start_bot()
    if success:
        send_telegram("✅ Bot restarted.")
    else:
        send_telegram("❌ Bot restart failed.")


def handle_stop() -> None:
    global _intentionally_stopped
    if not bot_is_running():
        return
    _intentionally_stopped = True
    kill_bot()
    drain_updates()  # skip messages that arrived while bot was running
    send_telegram("🛑 Bot stopped.")


def handle_start() -> None:
    global _intentionally_stopped
    if bot_is_running():
        return
    _intentionally_stopped = False
    start_bot()
    send_telegram("✅ Bot started.")


def handle_status() -> None:
    if bot_is_running():
        send_telegram("✅ Bot is running.")
    else:
        send_telegram("❌ Bot is not running.")


def _process_command(cmd: str) -> None:
    """Dispatch a single command string to the appropriate handler."""
    cmd = cmd.strip().lower()
    if cmd == "restart":
        handle_restart()
    elif cmd == "stop":
        handle_stop()
    elif cmd == "start":
        handle_start()
    elif cmd == "status":
        handle_status()
    else:
        log.warning("Unknown command: %r", cmd)


# ── FIFO / event loop ─────────────────────────────────────────────────────────

def ensure_pipe() -> None:
    """Create the named FIFO at PIPE_PATH if it does not already exist."""
    if PIPE_PATH.exists():
        if not stat.S_ISFIFO(PIPE_PATH.stat().st_mode):
            PIPE_PATH.unlink()
            os.mkfifo(PIPE_PATH)
    else:
        PIPE_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(PIPE_PATH)


def run_loop() -> None:
    """Main event loop: read commands from FIFO and run health checks."""
    global _intentionally_stopped
    ensure_pipe()
    log.info("Watchdog started. Listening on %s", PIPE_PATH)
    send_telegram("👀 Watchdog started.")

    fd = os.open(str(PIPE_PATH), os.O_RDONLY | os.O_NONBLOCK)
    try:
        buf = ""
        while True:
            ready, _, _ = select.select([fd], [], [], 5.0)
            if ready:
                chunk = os.read(fd, 1024).decode("utf-8", errors="replace")
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        log.info("Command received: %r", line)
                        _process_command(line)
            else:
                # Health check: if bot died unexpectedly, auto-restart
                if not _intentionally_stopped and not bot_is_running():
                    log.warning("Bot not running — auto-restarting")
                    send_telegram("⚠️ Bot crashed — restarted.")
                    start_bot()
                # Reply to incoming messages when bot is intentionally stopped
                elif _intentionally_stopped:
                    for update in get_updates():
                        msg = update.get("message") or update.get("edited_message")
                        if msg and msg.get("chat", {}).get("id") == CHAT_ID:
                            send_telegram("🛑 Bot stopped.")
    finally:
        os.close(fd)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    run_loop()


if __name__ == "__main__":
    main()
