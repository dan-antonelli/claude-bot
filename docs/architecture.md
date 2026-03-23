# Architecture

## System diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your machine                             │
│                                                                 │
│  ┌─────────────────────────┐   ┌─────────────────────────────┐ │
│  │   tmux: claude-bot      │   │   tmux: claude-watchdog     │ │
│  │                         │   │                             │ │
│  │  ┌───────────────────┐  │   │  ┌───────────────────────┐  │ │
│  │  │     bot.py        │  │   │  │     watchdog.py        │  │ │
│  │  │                   │  │   │  │                        │  │ │
│  │  │  asyncio event    │  │   │  │  monitors bot tmux     │  │ │
│  │  │  loop + lock      │  │   │  │  session health        │  │ │
│  │  │                   │  │   │  │                        │  │ │
│  │  │  spawns claude -p │  │   │  │  reads /tmp/           │  │ │
│  │  │  subprocess per   │◄─┼───┼──│  claude-bot.fifo      │  │ │
│  │  │  message          │  │   │  │  (named pipe)          │  │ │
│  │  └────────┬──────────┘  │   │  └──────────┬────────────┘  │ │
│  │           │             │   │             │                │ │
│  │  ┌────────▼──────────┐  │   │             │                │ │
│  │  │  claude -p        │  │   │             │                │ │
│  │  │  (subprocess)     │  │   │             │                │ │
│  │  │                   │  │   │             │                │ │
│  │  │  stream-json      │  │   │             │                │ │
│  │  │  stdout           │  │   │             │                │ │
│  │  └───────────────────┘  │   │             │                │ │
│  └─────────────────────────┘   └─────────────┼───────────────┘ │
│                                              │                  │
│         projects.json, .env ◄────────────────┘                  │
└──────────────────────┬──────────────────────┬───────────────────┘
                       │                      │
                       │ HTTPS polling         │ HTTPS (sendMessage)
                       │                      │
                       ▼                      ▼
              ┌─────────────────────────────────────┐
              │           Telegram API              │
              │        api.telegram.org             │
              └──────────────────┬──────────────────┘
                                 │
                                 │ push notification
                                 ▼
                        ┌─────────────────┐
                        │  Your Telegram  │
                        │  app / phone    │
                        └─────────────────┘
```

## Request flow (normal message)

```
You (Telegram) ──► Telegram API ──► bot.py (polling)
                                         │
                              acquire asyncio.Lock
                                         │
                              send "▶ <project>" to Telegram
                                         │
                         ┌───────────────┴──────────────────┐
                         │                                  │
                  typing_loop task                    run_claude()
                  (send "typing"                      spawn: claude -p
                   every 4 s)                         stream stdout
                         │                                  │
                         │               for each tool_use event:
                         │                   send "⚙️ Tool: …" to Telegram
                         │                                  │
                         │               on result event:
                  typing_done.set()          save session_id
                         │                  send result text to Telegram
                         │                                  │
                         └───────────────┬──────────────────┘
                                   release lock
```

## Restart flow (via watchdog)

```
You (Telegram) ──► Claude Code (in project dir)
                         │
                   echo restart > /tmp/claude-bot.fifo
                         │
                         ▼
                   watchdog.py (reads pipe)
                         │
                   send "🔄 Restarting bot..." to Telegram
                         │
                   tmux kill-session -t claude-bot
                         │
                   bash start-bot.sh
                         │
                   poll bot_is_running() up to 3 s
                         │
                   send "✅ Bot restarted." to Telegram
```

## Components

| Component | File | tmux session | Role |
|---|---|---|---|
| Bot | `bot.py` | `claude-bot` | Handles Telegram messages, invokes Claude |
| Watchdog | `watchdog/watchdog.py` | `claude-watchdog` | Lifecycle control, crash recovery |
| Launcher (bot) | `start-bot.sh` | — | Starts bot in tmux |
| Launcher (watchdog) | `watchdog/start.sh` | — | Starts watchdog in tmux |
| Config | `projects.json` | — | Project name → directory mapping |
| Secrets | `.env` | — | Bot token, chat ID, binary path, pipe path |

## Key design decisions

- **Single asyncio.Lock**: only one Claude invocation runs at a time; concurrent messages queue behind the lock rather than being dropped.
- **stream-json output**: Claude's `--output-format stream-json --include-partial-messages` allows the bot to send tool-use notifications in real time, before the final result arrives.
- **Named pipe (FIFO) for watchdog IPC**: one-way, no server loop, no new dependencies. Claude writes `echo restart > /tmp/claude-bot.fifo`; watchdog reads it within a 5-second poll cycle.
- **Watchdog independence**: the watchdog is not a child of the bot. Killing the bot does not affect the watchdog, which is why it can reliably restart it.
- **10 MB StreamReader limit**: the default 64 KB asyncio subprocess buffer is too small for Claude's JSON output when working with large files. Raised to 10 MB.
