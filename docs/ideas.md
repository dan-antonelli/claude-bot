# Ideas & Future Improvements

## 1. Zero-downtime deployments

Currently, updating the bot requires stopping it, applying changes, and restarting — which drops any in-flight Telegram sessions. Two approaches worth exploring:

- **Blue/green switching**: run two instances (old and new), flip traffic to the new one once it's healthy, then stop the old. Could be scripted around `start-bot.sh` and tmux.
- **Docker**: containerize the bot so updates become image swaps (`docker stop` → `docker run` with the new image). Also improves portability and makes the setup reproducible without manual `pip3 install` steps.

---

## 2. Better README — Telegram setup section

The current Telegram setup section could be clearer. Ideas:

- Add a step-by-step walkthrough with screenshots or annotated output snippets.
- Explain common failure modes (wrong chat ID, token typo, bot not started) and how to diagnose them.
- Cover the `CLAUDE_BIN` env var more prominently — it's a common sticking point on machines where `claude` isn't on PATH.

---

## 3. Multi-factor authentication

The bot currently gates access on a single `TELEGRAM_CHAT_ID`. This is reasonable for personal use but could be hardened:

- **OTP / time-based code**: require a TOTP code (e.g. Google Authenticator) before the bot accepts commands in a new session.
- **Allowlist expansion**: support multiple chat IDs with per-user permissions (read-only vs. full access).
- **Session expiry**: automatically invalidate sessions after N hours of inactivity.

---

## 4. Persistent storage / database

All state (active project, session ID) is currently held in memory and lost on restart. A lightweight database layer would make the bot more robust:

- **SQLite** is the natural fit — zero infrastructure, file-based, already available in Python's stdlib.
- Store: active project per chat, session IDs, command history, audit log of prompts sent.
- Enables features like session restore after crash, per-user project assignments, and usage analytics.

---

## 5. Loading indicator while Claude is thinking

There is currently no feedback between sending a prompt and receiving the first tool-use notification — the chat just goes silent. This can feel broken on longer tasks.

- Use Telegram's `sendChatAction` with `typing` on a repeating interval while Claude is running.
- Cancel the action as soon as the first tool notification (or final response) is sent.
- Keeps the UX responsive without any changes to the Claude invocation logic.

---

## 6. Command aliases

Frequently used project switches or prompt prefixes require retyping every time. A lightweight alias system would reduce friction:

- Define aliases in a new `aliases.json` (or a section of `projects.json`) — e.g. `"narrat": "/use narrat"` or `"standup": "summarise what changed today across all projects"`.
- Trigger with a `/alias <name>` command or a configurable prefix character.
- Aliases that expand to full prompts get forwarded to Claude; aliases that expand to bot commands are handled locally.

---

## 7. Send screenshots to Claude

Claude is multimodal but the bot currently only handles text. Supporting image input would open up a useful class of prompts:

- Accept photos sent directly in the Telegram chat and pass them to Claude alongside the text prompt.
- Useful for sharing UI screenshots, error dialogs, diagrams, or handwritten notes for Claude to reason about.
- Telegram delivers photos as file IDs; download via `getFile`, encode as base64, and include in the `claude -p` invocation using the `--image` flag (or API equivalent).
- Could also support documents (PDF, PNG attachments) with the same pipeline.

---

## 8. Deploy on a remote server

Running the bot on a local machine means it goes offline whenever the machine sleeps or loses connectivity. A persistent remote host eliminates that:

- **VPS / cloud VM**: smallest tier on Hetzner, DigitalOcean, or Fly.io is enough. Run the bot in a tmux session or as a systemd service so it survives reboots.
- **Authentication**: the remote machine needs `claude` installed and authenticated — document the one-time setup steps (copy `.env`, run `claude login`).
- **Project directories**: projects live on the remote machine; either mirror them via git or work directly on the server. Ties in with the Docker idea for easier provisioning.

---

## 9. Multi-machine control from one Telegram chat

Telegram's polling model is exclusive — only one instance can hold a bot token at a time, so running the same bot on two machines causes split, unpredictable routing. The cleanest solution is a single bot that routes to named machines:

- Each machine runs its own `bot.py` but subscribes to a **shared message broker** (Redis pub/sub or a lightweight MQTT broker) instead of polling Telegram directly.
- A thin **router process** (deployable on any always-on host) holds the single Telegram token, receives all messages, and fans them out to the broker.
- Messages are addressed with a machine prefix — e.g. `/on laptop narrat: fix the bug` or `/on server deploy`. Each machine instance picks up only messages addressed to it and replies back through the broker to Telegram.
- The router tags all responses with the originating machine name so it's always clear which machine replied.
- Pairs naturally with the remote server and Docker ideas — the router is the only component that needs a public host; machine instances connect outbound and need no open ports.

---

## 10. Improved message headers

The current header is just the project name (e.g. `▶ narrat`). It could carry more context without becoming noisy:

- **Machine name**: prepend the hostname (`socket.gethostname()`) so replies are always traceable — e.g. `▶ laptop / narrat`. Critical when running on multiple machines.
- **Timestamp**: include the time the response was sent, useful for async workflows where you check Telegram later.
- **Richer format**: a single compact header line like `▶ laptop · narrat · 14:32` covers machine, project, and time without extra messages.
- The header format could be configurable via `.env` (e.g. `SHOW_HOSTNAME=true`) so single-machine setups stay minimal.

---

## 11. Integrations — Narrat and NovelCrafter

The bot currently treats all projects as generic code directories. Writing-focused tools deserve first-class support:

- **Narrat**: since the game content lives in `.txt` scene files, Claude can already read and edit them — but a dedicated integration could surface game-specific context (current scene list, variable state, recent changes) automatically with each prompt, without the user having to ask.
- **NovelCrafter**: if NovelCrafter exposes a local API or file-based export (codex entries, scene outlines, chapter drafts), the bot could inject that context into prompts — enabling things like "write the next scene consistent with the codex" without manual copy-paste.
- Both integrations would live as optional project types in `projects.json` (e.g. `"type": "narrat"`) so the bot can tailor its context injection per project.

---

## 12. General task automation via Telegram

Beyond Claude Code, the bot's architecture (Telegram → subprocess → response) generalises to any shell-based task:

- **Scheduled tasks**: trigger recurring jobs (git pull, backups, test runs) via `/run <task>` or on a cron schedule, with results sent to Telegram.
- **System monitoring**: report disk usage, running processes, or service health on demand or on threshold breach.
- **Script library**: define a set of named scripts in `tasks.json` (similar to `projects.json`) that map short command names to shell commands — e.g. `deploy`, `backup`, `status`.
- This turns the bot into a general remote-control interface for the machine, not just a Claude Code bridge.

---

## 13. Switchable AI backend

The bot is hardcoded to invoke `claude`. Making the backend configurable would allow switching to other CLI-based AI tools without rewriting the bot:

- **Supported backends**: Cursor CLI, the OpenAI CLI (`chatgpt`), Gemini CLI, or any tool that accepts a prompt via stdin/args and streams output.
- Switch with a command like `/model cursor` or `/model chatgpt`, stored per-session or globally in `.env`.
- Each backend gets a small adapter (argument format, output parsing) since their CLI interfaces differ. The rest of the bot — Telegram handling, tool notifications, session management — stays unchanged.
- Useful for cost management (swap to a cheaper model for simple tasks) or capability comparison.

---

## 14. Start and stop bot instances from Telegram

Currently, starting the bot requires SSH or physical access to the machine. A lightweight management layer would allow lifecycle control from Telegram itself:

- A minimal **watchdog process** runs permanently (e.g. as a systemd service) and listens for `/start`, `/stop`, and `/restart` commands over a side-channel (a named pipe, a local HTTP endpoint, or a second lightweight bot token).
- The watchdog starts/stops the main `bot.py` process in response, and reports status back.
- Useful for applying updates: push new code, send `/restart` from Telegram, done — no SSH needed.
- Could also support `/update` which does a `git pull` and restarts in one step.

---

## 15. Telegram wrappers for Claude Code modes and commands

Claude Code has a rich set of interactive modes and slash commands that are unavailable in non-interactive `-p` mode. These could be exposed as Telegram bot commands by wrapping the prompt with the appropriate instruction prefix:

- `/plan <prompt>` — prepends "Plan the following task step by step. Do not write or modify any code — only describe your approach:" before forwarding to Claude.
- `/review` — asks Claude to review the current state of the active project without making changes.
- `/commit` — triggers a commit workflow: Claude stages, writes a message, and commits.
- `/test` — runs the project's test suite and reports results.
- `/explain <prompt>` — asks Claude to explain a piece of code or behaviour without changing anything.
- `/ask <prompt>` — pure Q&A mode, no file modifications allowed (via `--allowedTools` restriction).

Each wrapper is just a bot command that prepends a fixed system instruction to the user's message and optionally adjusts the `--allowedTools` flag passed to `claude -p`. No changes to Claude itself are needed — the behaviour is shaped entirely by the prompt.

---

## 16. Dynamic configuration — live reload without restart

Some configuration (aliases, project list, tool permissions) currently requires editing files and restarting the bot to take effect. A live-reloadable config layer would allow changes to be applied instantly from Telegram itself:

- **Storage**: SQLite is the natural fit — a single `config.db` holds all mutable config (aliases, projects, settings) and is read on every request, so changes are picked up immediately with no restart.
- **Manage from Telegram**: dedicated commands to create, update, and remove config entries on the fly:
  - `/alias add <name> <expansion>` — define a new alias (e.g. `/alias add standup "summarise what changed today"`)
  - `/alias remove <name>` — delete an alias
  - `/alias list` — show all current aliases
  - Same pattern for projects: `/project add <name> <path>`, `/project remove <name>`
- **Fallback**: JSON files (`aliases.json`, `projects.json`) remain as the seed/default config on first run; the database is populated from them and takes over from there.
- **Hot path**: on each incoming message, the bot checks the alias table first — if the message matches a defined alias, it expands it before forwarding to Claude. No bot restart, no file editing, no SSH.

---

## 17. Model instance management from Telegram

The bot currently has no visibility into what Claude processes are actually running on the machine. A `/instances` command would expose that and allow full lifecycle control from Telegram:

- **List**: `/instances` shows all running `claude` processes — project name, session ID, how long they've been running, and current status (thinking, waiting, idle).
- **Kill**: `/kill <project>` terminates a stuck or unwanted Claude process for a given project and clears its session.
- **Restart**: `/restart <project>` kills the current process and starts a fresh Claude session in that project's directory.
- **Start**: `/start <project>` launches a new Claude session for a project that has none active, without sending a prompt — useful for warming up a session before you're ready to use it.
- Implementation: track subprocess handles in the existing `sessions` dict (or a parallel `processes` dict), and expose the lifecycle commands as Telegram bot handlers. `/kill` sends `SIGTERM`; `/restart` does kill + start in sequence.
- Pairs naturally with the watchdog idea (idea 14) — together they give full remote control over both the bot process itself and the Claude subprocesses it manages.

---

## 18. Task queue with side-channel messaging

Currently, messages sent while Claude is working are implicitly queued by the asyncio lock — they run sequentially, one after another. But there is no way to interact with the queue or send a side note while a task is in flight.

- **`/queue`**: show what tasks are waiting (message text, time queued). Makes the implicit queue visible.
- **`/cancel`**: drop the next queued task without running it, or cancel the currently running one (sends `SIGTERM` to the Claude subprocess and releases the lock).
- **`/btw <note>`**: append a follow-up note to the *currently running* prompt. Implementation options:
  - Simple: buffer the note and prepend it to the next queued message as context ("Previously you were asked to X; also note: Y").
  - Advanced: inject it into the live Claude session mid-run by writing to the subprocess stdin (only viable if Claude supports mid-session injection, which it currently does not in `-p` mode — so the simple buffering approach is more realistic).
- **`/skip`**: discard all queued messages and only run the most recently sent one — useful when you've changed your mind mid-task.
- The queue itself is just a Python `asyncio.Queue` replacing the current implicit lock-wait behaviour. Each item holds the message text and the originating `Update` object so replies go back to the right chat.
