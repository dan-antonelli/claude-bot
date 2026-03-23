#!/usr/bin/env python3
"""
Claude Code Telegram Bot
Controls any Claude Code project from Telegram.
One instance per machine; switch projects with /use <name>.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID     = int(os.environ["TELEGRAM_CHAT_ID"])
CLAUDE_BIN  = os.environ.get("CLAUDE_BIN", "claude")
PROJECTS_FILE = Path(__file__).parent / "projects.json"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

def load_projects() -> list[dict]:
    with open(PROJECTS_FILE) as f:
        return json.load(f)

projects: list[dict] = load_projects()
active_project: str = projects[0]["name"]
sessions: dict[str, str] = {}  # project_name → session_id
lock = asyncio.Lock()


def get_project(name: str) -> Optional[dict]:
    return next((p for p in projects if p["name"] == name), None)

def active_dir() -> str:
    return get_project(active_project)["dir"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def truncate(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…"

async def send(update: Update, text: str) -> None:
    await update.message.reply_text(truncate(text))

def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == CHAT_ID

async def typing_loop(update: Update, stop_event: asyncio.Event) -> None:
    """Send the Telegram 'typing' action every 4 s until stop_event is set."""
    while not stop_event.is_set():
        await update.effective_chat.send_action("typing")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=4)
        except asyncio.TimeoutError:
            pass


def tool_summary(name: str, inp: dict) -> str:
    """One-line summary of a tool call."""
    if name == "Read":
        return inp.get("file_path", "")
    if name == "Write":
        return inp.get("file_path", "")
    if name == "Edit":
        return inp.get("file_path", "")
    if name == "Bash":
        cmd = inp.get("command", "")
        return cmd[:80] + ("…" if len(cmd) > 80 else "")
    if name == "Glob":
        return inp.get("pattern", "")
    if name == "Grep":
        return f'"{inp.get("pattern","")}"'
    if name == "WebSearch":
        return inp.get("query", "")
    return json.dumps(inp)[:80]

# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_projects(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    lines = []
    for p in projects:
        marker = "▶" if p["name"] == active_project else "  "
        session_note = " [session active]" if p["name"] in sessions else ""
        lines.append(f"{marker} {p['name']} — {p['dir']}{session_note}")
    await send(update, "\n".join(lines))

async def cmd_use(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    global active_project
    if not is_authorized(update):
        return
    args = (update.message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await send(update, "Usage: /use <project-name>")
        return
    name = args[1].strip()
    if not get_project(name):
        names = ", ".join(p["name"] for p in projects)
        await send(update, f"Unknown project '{name}'. Available: {names}")
        return
    active_project = name
    session_note = " (existing session)" if name in sessions else " (no session yet)"
    await send(update, f"Switched to {name}{session_note}")

async def cmd_new(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    sessions.pop(active_project, None)
    await send(update, f"Session cleared for {active_project}. Next message starts fresh.")

async def cmd_session(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    sid = sessions.get(active_project)
    if sid:
        await send(update, f"Project: {active_project}\nSession: {sid}")
    else:
        await send(update, f"Project: {active_project}\nNo session yet.")

async def cmd_reload(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    global projects
    if not is_authorized(update):
        return
    projects = load_projects()
    await send(update, f"Reloaded {len(projects)} projects.")

# ── Claude invocation ─────────────────────────────────────────────────────────

async def run_claude(user_text: str, update: Update, typing_done: asyncio.Event) -> None:
    project = get_project(active_project)
    cwd = project["dir"]
    session_id = sessions.get(active_project)

    args = [
        CLAUDE_BIN, "-p", user_text,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebSearch",
    ]
    if session_id:
        args += ["--resume", session_id]

    log.info("Running claude in %s (session=%s)", cwd, session_id or "new")
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=10 * 1024 * 1024,  # 10 MB — default 64 KB is too small for large Claude output
    )

    seen_tools: set[str] = set()
    result_text = ""
    new_session_id = None

    async for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        # Tool use notifications
        if etype == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    key = block.get("id", "")
                    if key not in seen_tools:
                        seen_tools.add(key)
                        name = block["name"]
                        summary = tool_summary(name, block.get("input", {}))
                        typing_done.set()
                        await update.message.reply_text(f"⚙️ {name}: {summary}")

        # Final result
        elif etype == "result":
            result_text = event.get("result", "").strip()
            new_session_id = event.get("session_id")

    await proc.wait()

    # Save session for continuity
    if new_session_id:
        sessions[active_project] = new_session_id
        log.info("Saved session %s for project %s", new_session_id, active_project)

    typing_done.set()
    if result_text:
        await send(update, result_text)
    else:
        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        err = stderr[:500] if stderr else "Claude returned no output."
        await send(update, f"⚠️ {err}")

# ── Message handler ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    if lock.locked():
        await send(update, "⏳ Still working… your message is queued.")

    async with lock:
        proj = get_project(active_project)
        await send(update, f"▶ {proj['name']}")
        try:
            await run_claude(user_text, update)
        except Exception as e:
            log.exception("Error running claude")
            await send(update, f"⚠️ Error: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("use",      cmd_use))
    app.add_handler(CommandHandler("new",      cmd_new))
    app.add_handler(CommandHandler("session",  cmd_session))
    app.add_handler(CommandHandler("reload",   cmd_reload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Bot started. Active project: %s", active_project)
    log.info("Projects: %s", [p["name"] for p in projects])

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
