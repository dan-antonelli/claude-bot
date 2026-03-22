"""
Tests for bot.py

conftest.py sets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before this module
is imported, so the module-level env reads in bot.py succeed.
"""

import json
import os
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

import bot


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_update(text: str = "", chat_id: int = 999) -> MagicMock:
    """Build a minimal mock telegram Update."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def make_context() -> MagicMock:
    return MagicMock()


# ── truncate ──────────────────────────────────────────────────────────────────

class TestTruncate:
    def test_short_string_unchanged(self):
        assert bot.truncate("hello") == "hello"

    def test_empty_string_unchanged(self):
        assert bot.truncate("") == ""

    def test_exact_limit_unchanged(self):
        s = "x" * 4000
        assert bot.truncate(s) == s

    def test_over_limit_truncated(self):
        s = "x" * 5000
        result = bot.truncate(s)
        assert result.endswith("\n…")
        assert len(result) == 4000 + 2  # 4000 chars + "\n…"

    def test_custom_limit(self):
        result = bot.truncate("abcdef", limit=3)
        assert result == "abc\n…"

    def test_one_over_limit(self):
        s = "x" * 4001
        result = bot.truncate(s)
        assert result == "x" * 4000 + "\n…"


# ── tool_summary ──────────────────────────────────────────────────────────────

class TestToolSummary:
    def test_read(self):
        assert bot.tool_summary("Read", {"file_path": "/foo/bar.py"}) == "/foo/bar.py"

    def test_write(self):
        assert bot.tool_summary("Write", {"file_path": "/out.txt"}) == "/out.txt"

    def test_edit(self):
        assert bot.tool_summary("Edit", {"file_path": "/edit.py"}) == "/edit.py"

    def test_bash_short(self):
        assert bot.tool_summary("Bash", {"command": "ls -la"}) == "ls -la"

    def test_bash_long_truncated(self):
        cmd = "echo " + "x" * 100
        result = bot.tool_summary("Bash", {"command": cmd})
        assert result.endswith("…")
        assert len(result) == 81  # 80 chars + "…"

    def test_bash_exactly_80(self):
        cmd = "x" * 80
        result = bot.tool_summary("Bash", {"command": cmd})
        assert result == cmd  # no ellipsis

    def test_glob(self):
        assert bot.tool_summary("Glob", {"pattern": "**/*.py"}) == "**/*.py"

    def test_grep(self):
        assert bot.tool_summary("Grep", {"pattern": "def foo"}) == '"def foo"'

    def test_websearch(self):
        assert bot.tool_summary("WebSearch", {"query": "pytest docs"}) == "pytest docs"

    def test_unknown_tool_json_fallback(self):
        result = bot.tool_summary("UnknownTool", {"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_unknown_tool_long_truncated(self):
        inp = {"key": "v" * 200}
        result = bot.tool_summary("UnknownTool", inp)
        assert len(result) <= 80

    def test_missing_keys_return_empty(self):
        assert bot.tool_summary("Read", {}) == ""
        assert bot.tool_summary("Glob", {}) == ""


# ── get_project ───────────────────────────────────────────────────────────────

class TestGetProject:
    def setup_method(self):
        self._orig = bot.projects[:]

    def teardown_method(self):
        bot.projects[:] = self._orig

    def test_found(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}, {"name": "beta", "dir": "/b"}]
        result = bot.get_project("alpha")
        assert result == {"name": "alpha", "dir": "/a"}

    def test_not_found(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}]
        assert bot.get_project("nonexistent") is None

    def test_returns_first_match(self):
        bot.projects = [
            {"name": "dup", "dir": "/first"},
            {"name": "dup", "dir": "/second"},
        ]
        result = bot.get_project("dup")
        assert result["dir"] == "/first"

    def test_empty_list(self):
        bot.projects = []
        assert bot.get_project("anything") is None


# ── is_authorized ─────────────────────────────────────────────────────────────

class TestIsAuthorized:
    def test_authorized(self):
        update = make_update(chat_id=999)
        assert bot.is_authorized(update) is True

    def test_unauthorized(self):
        update = make_update(chat_id=12345)
        assert bot.is_authorized(update) is False

    def test_zero_chat_id_unauthorized(self):
        update = make_update(chat_id=0)
        assert bot.is_authorized(update) is False


# ── load_projects ─────────────────────────────────────────────────────────────

class TestLoadProjects:
    def test_loads_valid_json(self, tmp_path):
        data = [{"name": "proj", "dir": "/some/path"}]
        f = tmp_path / "projects.json"
        f.write_text(json.dumps(data))
        with patch.object(bot, "PROJECTS_FILE", f):
            result = bot.load_projects()
        assert result == data

    def test_loads_multiple_projects(self, tmp_path):
        data = [
            {"name": "a", "dir": "/a"},
            {"name": "b", "dir": "/b"},
            {"name": "c", "dir": "/c"},
        ]
        f = tmp_path / "projects.json"
        f.write_text(json.dumps(data))
        with patch.object(bot, "PROJECTS_FILE", f):
            result = bot.load_projects()
        assert len(result) == 3


# ── Command handlers ───────────────────────────────────────────────────────────

class TestCmdProjects:
    def setup_method(self):
        self._orig_projects = bot.projects[:]
        self._orig_active = bot.active_project
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.projects[:] = self._orig_projects
        bot.active_project = self._orig_active
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_lists_projects_with_marker(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}, {"name": "beta", "dir": "/b"}]
        bot.active_project = "alpha"
        bot.sessions.clear()

        update = make_update()
        await bot.cmd_projects(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "▶ alpha" in text
        assert "beta" in text
        assert "▶ beta" not in text

    async def test_shows_session_active_note(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}]
        bot.active_project = "alpha"
        bot.sessions["alpha"] = "sess-123"

        update = make_update()
        await bot.cmd_projects(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "[session active]" in text

    async def test_ignores_unauthorized(self):
        update = make_update(chat_id=0)
        await bot.cmd_projects(update, make_context())
        update.message.reply_text.assert_not_called()


class TestCmdUse:
    def setup_method(self):
        self._orig_projects = bot.projects[:]
        self._orig_active = bot.active_project
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.projects[:] = self._orig_projects
        bot.active_project = self._orig_active
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_switches_project(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}, {"name": "beta", "dir": "/b"}]
        bot.active_project = "alpha"

        update = make_update(text="/use beta")
        await bot.cmd_use(update, make_context())

        assert bot.active_project == "beta"

    async def test_unknown_project_error(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}]
        bot.active_project = "alpha"

        update = make_update(text="/use nonexistent")
        await bot.cmd_use(update, make_context())

        assert bot.active_project == "alpha"
        text = update.message.reply_text.call_args[0][0]
        assert "Unknown project" in text
        assert "nonexistent" in text

    async def test_no_args_shows_usage(self):
        update = make_update(text="/use")
        await bot.cmd_use(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_session_note_no_session(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}, {"name": "beta", "dir": "/b"}]
        bot.sessions.clear()

        update = make_update(text="/use beta")
        await bot.cmd_use(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "no session" in text

    async def test_session_note_existing_session(self):
        bot.projects = [{"name": "alpha", "dir": "/a"}, {"name": "beta", "dir": "/b"}]
        bot.sessions["beta"] = "existing-session"

        update = make_update(text="/use beta")
        await bot.cmd_use(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "existing session" in text

    async def test_ignores_unauthorized(self):
        orig = bot.active_project
        update = make_update(text="/use beta", chat_id=0)
        await bot.cmd_use(update, make_context())
        assert bot.active_project == orig
        update.message.reply_text.assert_not_called()


class TestCmdNew:
    def setup_method(self):
        self._orig_active = bot.active_project
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.active_project = self._orig_active
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_clears_session(self):
        bot.active_project = "narrat"
        bot.sessions["narrat"] = "old-session-id"

        update = make_update()
        await bot.cmd_new(update, make_context())

        assert "narrat" not in bot.sessions

    async def test_ok_when_no_session(self):
        bot.active_project = "narrat"
        bot.sessions.pop("narrat", None)

        update = make_update()
        await bot.cmd_new(update, make_context())

        update.message.reply_text.assert_called_once()

    async def test_confirms_with_project_name(self):
        bot.active_project = "narrat"

        update = make_update()
        await bot.cmd_new(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "narrat" in text

    async def test_ignores_unauthorized(self):
        update = make_update(chat_id=0)
        await bot.cmd_new(update, make_context())
        update.message.reply_text.assert_not_called()


class TestCmdSession:
    def setup_method(self):
        self._orig_active = bot.active_project
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.active_project = self._orig_active
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_shows_session_id(self):
        bot.active_project = "narrat"
        bot.sessions["narrat"] = "abc-123"

        update = make_update()
        await bot.cmd_session(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "abc-123" in text
        assert "narrat" in text

    async def test_no_session_message(self):
        bot.active_project = "narrat"
        bot.sessions.pop("narrat", None)

        update = make_update()
        await bot.cmd_session(update, make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "No session" in text

    async def test_ignores_unauthorized(self):
        update = make_update(chat_id=0)
        await bot.cmd_session(update, make_context())
        update.message.reply_text.assert_not_called()


class TestCmdReload:
    def setup_method(self):
        self._orig_projects = bot.projects[:]

    def teardown_method(self):
        bot.projects[:] = self._orig_projects

    async def test_reloads_and_confirms(self):
        new_data = [{"name": "fresh", "dir": "/fresh"}]
        with patch.object(bot, "load_projects", return_value=new_data):
            update = make_update()
            await bot.cmd_reload(update, make_context())

        assert bot.projects == new_data
        text = update.message.reply_text.call_args[0][0]
        assert "1" in text  # "Reloaded 1 projects"

    async def test_ignores_unauthorized(self):
        update = make_update(chat_id=0)
        await bot.cmd_reload(update, make_context())
        update.message.reply_text.assert_not_called()


# ── run_claude ─────────────────────────────────────────────────────────────────

def _make_stream(*events: dict):
    """Return an async iterator that yields JSON-encoded event lines."""
    lines = [json.dumps(e).encode() + b"\n" for e in events]

    class _AsyncIter:
        def __init__(self):
            self._lines = iter(lines)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._lines)
            except StopIteration:
                raise StopAsyncIteration

    return _AsyncIter()


def _make_proc(stdout_events: list[dict], returncode: int = 0, stderr: bytes = b""):
    proc = MagicMock()
    proc.stdout = _make_stream(*stdout_events)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    return proc


class TestRunClaude:
    def setup_method(self):
        self._orig_active = bot.active_project
        self._orig_projects = bot.projects[:]
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.active_project = self._orig_active
        bot.projects[:] = self._orig_projects
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_sends_result_text(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        events = [
            {"type": "result", "result": "All done!", "session_id": "new-sess"},
        ]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            update = make_update()
            await bot.run_claude("do something", update)

        update.message.reply_text.assert_called_with("All done!")

    async def test_saves_session_id(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        events = [
            {"type": "result", "result": "done", "session_id": "saved-session"},
        ]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            await bot.run_claude("task", make_update())

        assert bot.sessions["narrat"] == "saved-session"

    async def test_resumes_existing_session(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions["narrat"] = "prior-session"

        events = [{"type": "result", "result": "ok", "session_id": "prior-session"}]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await bot.run_claude("task", make_update())

        call_args = mock_exec.call_args[0]
        assert "--resume" in call_args
        idx = list(call_args).index("--resume")
        assert call_args[idx + 1] == "prior-session"

    async def test_no_resume_for_new_session(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        events = [{"type": "result", "result": "ok", "session_id": "s"}]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await bot.run_claude("task", make_update())

        call_args = mock_exec.call_args[0]
        assert "--resume" not in call_args

    async def test_sends_tool_use_notifications(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/foo.py"}},
                    ]
                },
            },
            {"type": "result", "result": "done", "session_id": "s"},
        ]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            update = make_update()
            await bot.run_claude("task", update)

        calls = [c[0][0] for c in update.message.reply_text.call_args_list]
        tool_calls = [c for c in calls if c.startswith("⚙️")]
        assert len(tool_calls) == 1
        assert "Read" in tool_calls[0]
        assert "/foo.py" in tool_calls[0]

    async def test_deduplicates_tool_notifications(self):
        """The same tool_use id should only produce one notification."""
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        tool_block = {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/a.py"}}
        events = [
            {"type": "assistant", "message": {"content": [tool_block]}},
            {"type": "assistant", "message": {"content": [tool_block]}},  # duplicate
            {"type": "result", "result": "done", "session_id": "s"},
        ]
        proc = _make_proc(events)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            update = make_update()
            await bot.run_claude("task", update)

        calls = [c[0][0] for c in update.message.reply_text.call_args_list]
        tool_calls = [c for c in calls if c.startswith("⚙️")]
        assert len(tool_calls) == 1

    async def test_stderr_on_no_result(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        proc = _make_proc([], stderr=b"some error occurred")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            update = make_update()
            await bot.run_claude("task", update)

        text = update.message.reply_text.call_args[0][0]
        assert "⚠️" in text
        assert "some error occurred" in text

    async def test_fallback_message_when_no_stderr(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        proc = _make_proc([], stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            update = make_update()
            await bot.run_claude("task", update)

        text = update.message.reply_text.call_args[0][0]
        assert "⚠️" in text

    async def test_ignores_non_json_lines(self):
        bot.active_project = "narrat"
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.sessions.clear()

        class _MixedStream:
            def __aiter__(self):
                return self
            _items = iter([
                b"not json\n",
                b"\n",
                json.dumps({"type": "result", "result": "ok", "session_id": "s"}).encode() + b"\n",
            ])
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        proc = _make_proc([], stderr=b"")
        proc.stdout = _MixedStream()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            update = make_update()
            await bot.run_claude("task", update)

        update.message.reply_text.assert_called_with("ok")


# ── handle_message ────────────────────────────────────────────────────────────

class TestHandleMessage:
    def setup_method(self):
        self._orig_active = bot.active_project
        self._orig_projects = bot.projects[:]
        self._orig_sessions = dict(bot.sessions)

    def teardown_method(self):
        bot.active_project = self._orig_active
        bot.projects[:] = self._orig_projects
        bot.sessions.clear()
        bot.sessions.update(self._orig_sessions)

    async def test_ignores_empty_message(self):
        update = make_update(text="   ")
        with patch.object(bot, "run_claude", new=AsyncMock()) as mock_run:
            await bot.handle_message(update, make_context())
        mock_run.assert_not_called()

    async def test_ignores_unauthorized(self):
        update = make_update(text="do something", chat_id=0)
        with patch.object(bot, "run_claude", new=AsyncMock()) as mock_run:
            await bot.handle_message(update, make_context())
        mock_run.assert_not_called()

    async def test_calls_run_claude_with_text(self):
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.active_project = "narrat"

        update = make_update(text="hello claude")
        with patch.object(bot, "run_claude", new=AsyncMock()) as mock_run:
            await bot.handle_message(update, make_context())

        mock_run.assert_awaited_once_with("hello claude", update)

    async def test_sends_project_name_before_running(self):
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.active_project = "narrat"

        update = make_update(text="hello")
        with patch.object(bot, "run_claude", new=AsyncMock()):
            await bot.handle_message(update, make_context())

        first_call_text = update.message.reply_text.call_args_list[0][0][0]
        assert "narrat" in first_call_text

    async def test_exception_in_run_claude_sends_error(self):
        bot.projects = [{"name": "narrat", "dir": "/tmp"}]
        bot.active_project = "narrat"

        update = make_update(text="crash please")
        with patch.object(bot, "run_claude", new=AsyncMock(side_effect=RuntimeError("boom"))):
            await bot.handle_message(update, make_context())

        calls = [c[0][0] for c in update.message.reply_text.call_args_list]
        error_msgs = [c for c in calls if "⚠️" in c]
        assert error_msgs
        assert "boom" in error_msgs[0]
