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
