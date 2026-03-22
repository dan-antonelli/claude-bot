# Ideas & Future Improvements

## Zero-downtime deployments

Currently, updating the bot requires stopping it, applying changes, and restarting — which drops any in-flight Telegram sessions. Two approaches worth exploring:

- **Blue/green switching**: run two instances (old and new), flip traffic to the new one once it's healthy, then stop the old. Could be scripted around `start-bot.sh` and tmux.
- **Docker**: containerize the bot so updates become image swaps (`docker stop` → `docker run` with the new image). Also improves portability and makes the setup reproducible without manual `pip3 install` steps.

---

## Better README — Telegram setup section

The current Telegram setup section could be clearer. Ideas:

- Add a step-by-step walkthrough with screenshots or annotated output snippets.
- Explain common failure modes (wrong chat ID, token typo, bot not started) and how to diagnose them.
- Cover the `CLAUDE_BIN` env var more prominently — it's a common sticking point on machines where `claude` isn't on PATH.

---

## Multi-factor authentication

The bot currently gates access on a single `TELEGRAM_CHAT_ID`. This is reasonable for personal use but could be hardened:

- **OTP / time-based code**: require a TOTP code (e.g. Google Authenticator) before the bot accepts commands in a new session.
- **Allowlist expansion**: support multiple chat IDs with per-user permissions (read-only vs. full access).
- **Session expiry**: automatically invalidate sessions after N hours of inactivity.

---

## Persistent storage / database

All state (active project, session ID) is currently held in memory and lost on restart. A lightweight database layer would make the bot more robust:

- **SQLite** is the natural fit — zero infrastructure, file-based, already available in Python's stdlib.
- Store: active project per chat, session IDs, command history, audit log of prompts sent.
- Enables features like session restore after crash, per-user project assignments, and usage analytics.

---

## Loading indicator while Claude is thinking

There is currently no feedback between sending a prompt and receiving the first tool-use notification — the chat just goes silent. This can feel broken on longer tasks.

- Use Telegram's `sendChatAction` with `typing` on a repeating interval while Claude is running.
- Cancel the action as soon as the first tool notification (or final response) is sent.
- Keeps the UX responsive without any changes to the Claude invocation logic.

---

## Command aliases

Frequently used project switches or prompt prefixes require retyping every time. A lightweight alias system would reduce friction:

- Define aliases in a new `aliases.json` (or a section of `projects.json`) — e.g. `"narrat": "/use narrat"` or `"standup": "summarise what changed today across all projects"`.
- Trigger with a `/alias <name>` command or a configurable prefix character.
- Aliases that expand to full prompts get forwarded to Claude; aliases that expand to bot commands are handled locally.

---

## Send screenshots to Claude

Claude is multimodal but the bot currently only handles text. Supporting image input would open up a useful class of prompts:

- Accept photos sent directly in the Telegram chat and pass them to Claude alongside the text prompt.
- Useful for sharing UI screenshots, error dialogs, diagrams, or handwritten notes for Claude to reason about.
- Telegram delivers photos as file IDs; download via `getFile`, encode as base64, and include in the `claude -p` invocation using the `--image` flag (or API equivalent).
- Could also support documents (PDF, PNG attachments) with the same pipeline.

---

## Deploy on a remote server

Running the bot on a local machine means it goes offline whenever the machine sleeps or loses connectivity. A persistent remote host eliminates that:

- **VPS / cloud VM**: smallest tier on Hetzner, DigitalOcean, or Fly.io is enough. Run the bot in a tmux session or as a systemd service so it survives reboots.
- **Authentication**: the remote machine needs `claude` installed and authenticated — document the one-time setup steps (copy `.env`, run `claude login`).
- **Project directories**: projects live on the remote machine; either mirror them via git or work directly on the server. Ties in with the Docker idea for easier provisioning.

---

## Multi-machine control from one Telegram chat

Telegram's polling model is exclusive — only one instance can hold a bot token at a time, so running the same bot on two machines causes split, unpredictable routing. The cleanest solution is a single bot that routes to named machines:

- Each machine runs its own `bot.py` but subscribes to a **shared message broker** (Redis pub/sub or a lightweight MQTT broker) instead of polling Telegram directly.
- A thin **router process** (deployable on any always-on host) holds the single Telegram token, receives all messages, and fans them out to the broker.
- Messages are addressed with a machine prefix — e.g. `/on laptop narrat: fix the bug` or `/on server deploy`. Each machine instance picks up only messages addressed to it and replies back through the broker to Telegram.
- The router tags all responses with the originating machine name so it's always clear which machine replied.
- Pairs naturally with the remote server and Docker ideas — the router is the only component that needs a public host; machine instances connect outbound and need no open ports.

---

## Improved message headers

The current header is just the project name (e.g. `▶ narrat`). It could carry more context without becoming noisy:

- **Machine name**: prepend the hostname (`socket.gethostname()`) so replies are always traceable — e.g. `▶ laptop / narrat`. Critical when running on multiple machines.
- **Timestamp**: include the time the response was sent, useful for async workflows where you check Telegram later.
- **Richer format**: a single compact header line like `▶ laptop · narrat · 14:32` covers machine, project, and time without extra messages.
- The header format could be configurable via `.env` (e.g. `SHOW_HOSTNAME=true`) so single-machine setups stay minimal.
