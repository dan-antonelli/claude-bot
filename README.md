# Claude Code Telegram Bot

Control any [Claude Code](https://docs.anthropic.com/en/docs/claude-code) project from Telegram. Send natural-language prompts from your phone and get responses back — including live tool-use notifications as Claude works.

One bot instance per machine. Switch between multiple projects on the fly with `/use <name>`.

---

## How it works

The bot runs on your machine alongside Claude Code. When you send a message:

1. The bot forwards it to `claude -p` (non-interactive mode) in the working directory of the active project.
2. While Claude works, the bot streams back a notification for each tool call (file reads, edits, bash commands, etc.).
3. Once Claude finishes, the bot sends you the final result.

Sessions are preserved between messages so Claude remembers context within a conversation. Use `/new` to start fresh.

---

## Prerequisites

- Python 3.9+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` on your PATH, or set `CLAUDE_BIN` in `.env`)
- A Telegram account
- [tmux](https://github.com/tmux/tmux) (used by `start-bot.sh` to keep the bot running in the background)

Install Python dependencies:

```bash
pip3 install python-telegram-bot python-dotenv
```

---

## Telegram setup

### 1. Create a bot with BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts — choose a name and username.
3. BotFather will give you a **bot token** that looks like `123456789:ABCdef...`. Save it.

### 2. Get your numeric chat ID

You need to lock the bot to your own Telegram account so nobody else can use it.

**Option A — using @userinfobot:**
1. Search for **@userinfobot** in Telegram and start it.
2. It will reply with your numeric user ID (e.g. `123456789`).

**Option B — using the Telegram API:**
1. Start your bot (send it `/start` or any message).
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
3. Find `"chat":{"id": ...}` in the JSON — that number is your chat ID.

---

## Installation

```bash
git clone <repo-url> ~/.claude-bot
cd ~/.claude-bot
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789
# Optional: path to the claude binary if it's not on PATH
CLAUDE_BIN=/Users/yourname/.local/bin/claude
```

Edit `projects.json` to list the directories you want to control:

```json
[
  {"name": "myapp",  "dir": "/Users/yourname/projects/myapp"},
  {"name": "website","dir": "/Users/yourname/projects/website"}
]
```

---

## Running the bot

### With tmux (recommended — keeps running after you close your terminal)

```bash
chmod +x start-bot.sh
./start-bot.sh
```

Useful tmux commands:
- **Attach to the session:** `tmux attach -t claude-bot`
- **Detach (leave running):** `Ctrl+B` then `D`
- **Stop the bot:** `tmux kill-session -t claude-bot`

### Directly

```bash
python3 bot.py
```

---

## Watchdog

The watchdog (`watchdog/watchdog.py`) is a small independent process that sits beside the bot and owns its lifecycle. It runs in a separate tmux session, has no dependency on the bot, and cannot be killed by the bot restarting.

**What it does:**
- Monitors the bot every 5 seconds. If the bot dies unexpectedly, it restarts it automatically.
- Accepts commands via a named pipe so you — or Claude — can trigger restarts, stops, and status checks without SSH.
- Sends Telegram notifications for every lifecycle event: startup, restart, stop, crash recovery.

**Why it exists:** the bot is Claude's parent process and communication channel. If Claude tries to restart the bot directly, it kills itself mid-execution and no reply is ever sent. The watchdog lives outside this loop — Claude writes a one-word command to a pipe and exits cleanly, then the watchdog handles the rest and confirms on Telegram.

### Starting the watchdog

```bash
chmod +x watchdog/start.sh
./watchdog/start.sh
```

Runs in its own tmux session (`claude-watchdog`), independent of `claude-bot`.

### Commands

Send commands by writing to the named pipe (default: `/tmp/claude-bot.fifo`):

```bash
echo restart > /tmp/claude-bot.fifo   # kill and relaunch the bot
echo stop    > /tmp/claude-bot.fifo   # stop the bot
echo start   > /tmp/claude-bot.fifo   # start the bot if it's not running
echo status  > /tmp/claude-bot.fifo   # check if the bot is running
```

The watchdog sends a Telegram message for each action (e.g. "🔄 Restarting bot..." then "✅ Bot restarted.").

**From Claude Code:** you can ask Claude to restart the bot and it will work correctly — Claude writes to the pipe and exits, the watchdog handles the rest and notifies you on Telegram.

### Crash recovery

If the bot dies unexpectedly while the watchdog is running, the watchdog automatically restarts it and sends "⚠️ Bot crashed — restarted." to Telegram.

### Production: keep the watchdog alive with launchd (macOS)

Running the watchdog in tmux works for development, but tmux sessions don't survive reboots. For production, install it as a launchd service so macOS keeps it alive permanently:

```bash
chmod +x watchdog/install-launchd.sh
./watchdog/install-launchd.sh
```

This stops the tmux session (if running), generates a plist at `~/Library/LaunchAgents/com.claude-bot.watchdog.plist`, and loads it. launchd will restart the watchdog on crash and on every login. The watchdog sends "👀 Watchdog started." to Telegram on each restart.

> **Note — macOS Full Disk Access:** if the repo lives in `~/Documents`, `~/Desktop`, or `~/Downloads`, macOS blocks the system `python3` from reading files there when run by launchd. Fix: open **System Settings → Privacy & Security → Full Disk Access** and add `python3` (at `/usr/bin/python3`) or your terminal app. Then reload: `launchctl unload ~/Library/LaunchAgents/com.claude-bot.watchdog.plist && ./watchdog/install-launchd.sh`.

Uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.claude-bot.watchdog.plist
rm ~/Library/LaunchAgents/com.claude-bot.watchdog.plist
```

### Config

Override the pipe path in `.env`:
```env
WATCHDOG_PIPE=/tmp/claude-bot.fifo
```

---

## Commands

| Command | Description |
|---|---|
| `/projects` | List all configured projects. The active one is marked with `▶`. |
| `/use <name>` | Switch the active project. |
| `/new` | Clear the Claude session for the current project (start a fresh conversation). |
| `/session` | Show the current project and session ID. |
| `/reload` | Reload `projects.json` from disk (pick up additions without restarting). |

Any non-command message is forwarded to Claude as a prompt in the active project's directory.

---

## Usage examples

```
You: refactor the login function to use async/await
Bot: ▶ myapp
Bot: ⚙️ Read: src/auth/login.js
Bot: ⚙️ Edit: src/auth/login.js
Bot: Done. The login function in src/auth/login.js now uses async/await...

You: /use website
Bot: Switched to website (no session yet)

You: what does the homepage hero section do?
Bot: ▶ website
Bot: ⚙️ Read: src/components/Hero.tsx
Bot: The Hero component renders a full-width banner with...
```

---

## Security

- The bot only responds to the single `TELEGRAM_CHAT_ID` configured in `.env`. All messages from other users are silently ignored.
- The `.env` file contains your bot token — keep it out of version control (it is in `.gitignore` by default).
- Claude runs with the `--allowedTools Bash,Read,Write,Edit,Glob,Grep,WebSearch` flag, which permits broad file system and shell access within the project directory. Only point this at directories you trust.

---

## Running tests

```bash
pip3 install pytest pytest-asyncio
pytest
```
