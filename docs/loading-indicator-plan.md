# Plan: Loading indicator (Telegram typing feedback)

**Branch:** `feature/loading-indicator`
**Status:** Implemented ✓

## Goal
Show the Telegram "typing…" indicator while Claude is working, so the user sees immediate feedback after sending a message.

## Changes — one file: `bot.py`

### Step 1 — `typing_loop` helper (Helpers section, after `tool_summary`)
Async function accepting `update` and `stop_event: asyncio.Event`. Sends `send_action("typing")` every 4 s (Telegram typing expires after 5 s, so 4 s keeps it alive). Exits as soon as the event is set.

### Step 2 — `run_claude` accepts `typing_done: asyncio.Event`
Calls `typing_done.set()` at two points:
- When the first tool-use notification is sent (⚙️ message) — earliest visible output
- Before the post-loop result/error block — catches the no-tool-calls path

### Step 3 — `handle_message` spawns and cleans up the task
Just before calling `run_claude`:
```python
typing_done = asyncio.Event()
typing_task = asyncio.create_task(typing_loop(update, typing_done))
```
Wraps the `run_claude` call in try/finally that sets the event and cancels the task — indicator always stops even if Claude errors out.

## No changes to
Claude invocation args, session logic, stream parsing, other bot commands.

## Version check
Requires python-telegram-bot ≥ v20 (async API). Installed: v22.5 ✓
