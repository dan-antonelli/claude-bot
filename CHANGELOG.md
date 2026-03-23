# Changelog

## [Unreleased]

### Changed
- `CLAUDE.md`: added rule to always update `CHANGELOG.md` after every committed change

---

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.0.1-alpha] - 2026-03-22

Initial working release.

### Added

**Core bot**
- Telegram bot (`bot.py`) that forwards natural-language messages to `claude -p` and streams tool-use notifications back in real time
- Session persistence: each project conversation resumes via `--resume` across messages
- Multi-project support configured in `projects.json`
- `/projects` command to list configured projects
- `/switch <project>` to change the active project
- `/cancel` to abort an in-progress Claude invocation
- `/session` to display the current session ID
- Typing indicator while Claude is running
- Startup greeting sent to Telegram when the bot starts
- Shutdown notification sent to Telegram when the bot stops
- Authorization: only responds to the configured `TELEGRAM_CHAT_ID`; all other chat IDs are silently ignored
- 59-test pytest suite covering truncation, tool summaries, project commands, session handling, and message flow

**Watchdog** (`watchdog/`)
- Independent watchdog process for bot lifecycle management
- Commands via named pipe (`/tmp/claude-bot.fifo`): `restart`, `stop`, `start`, `status`
- Auto-restart with Telegram notification on unexpected crash
- "👀 Watchdog started." notification on each watchdog launch
- "🛑 Bot stopped." reply to any incoming Telegram message while the bot is intentionally stopped
- launchd service installer (`watchdog/install-launchd.sh`) for permanent deployment that survives reboots

### Fixed
- `LimitOverrunError` on large Claude outputs — raised asyncio `StreamReader` limit to 10 MB
- launchd environment missing `tmux` in PATH — added explicit `PATH` to plist `EnvironmentVariables`
- launchd reinstall failing with `Load failed: 5` when service was already loaded — unload before reload
- launchd FDA requirement: service must be run by a Python binary with Full Disk Access granted in System Settings
