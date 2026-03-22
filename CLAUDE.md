# Claude Bot — Project Instructions

## Overview
This is a Telegram bot that forwards natural-language prompts to Claude Code (`claude -p`) and streams back tool-use notifications and results. One bot instance per machine; multiple projects configured in `projects.json`.

## Key files
- [bot.py](bot.py) — main bot logic (Telegram handlers, Claude invocation, session management)
- [projects.json](projects.json) — list of `{name, dir}` project entries
- [test_bot.py](test_bot.py) — pytest test suite
- [conftest.py](conftest.py) — pytest fixtures
- [.env](.env) — secrets (not committed); see [.env.example](.env.example)

## Running
```bash
./start-bot.sh          # via tmux (recommended)
python3 bot.py          # directly
```

## Testing
```bash
pytest
```

## Dependencies
```bash
pip3 install python-telegram-bot python-dotenv pytest pytest-asyncio
```

## Development approach
- **TDD**: write tests before implementation. A feature isn't started until its test exists.
- **Iterative**: keep running tests and fixing errors until everything passes. Never leave a task in a broken state.

## Architecture notes
- `run_claude()` spawns `claude -p` as a subprocess with `--output-format stream-json --verbose --include-partial-messages`
- Streams JSON events line-by-line: sends a Telegram notification per `tool_use` block, sends final result on `result` event
- Sessions are keyed by project name and passed via `--resume <session_id>` for conversation continuity
- A single `asyncio.Lock` serializes all Claude invocations — concurrent messages are queued, not dropped
- `TELEGRAM_CHAT_ID` is the only authorization check; all other chat IDs are silently ignored
