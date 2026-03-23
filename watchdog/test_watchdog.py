"""
Tests for watchdog.py

conftest.py sets TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and WATCHDOG_PIPE
before this module is imported.
"""

import json
import os
import urllib.error
import urllib.request
from unittest.mock import MagicMock, call, patch

import pytest

import watchdog


# ── TestSendTelegram ──────────────────────────────────────────────────────────

class TestSendTelegram:
    def test_posts_to_correct_url(self):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            watchdog.send_telegram("hello")
        url = mock_open.call_args[0][0].full_url
        assert watchdog.BOT_TOKEN in url

    def test_includes_chat_id_and_text(self):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            watchdog.send_telegram("test message")
        req = mock_open.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["chat_id"] == watchdog.CHAT_ID
        assert body["text"] == "test message"

    def test_does_not_raise_on_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network down")):
            # Should not raise
            watchdog.send_telegram("oops")


# ── TestBotIsRunning ──────────────────────────────────────────────────────────

class TestBotIsRunning:
    def test_true_when_session_exists(self):
        result = MagicMock()
        result.returncode = 0
        with patch("subprocess.run", return_value=result):
            assert watchdog.bot_is_running() is True

    def test_false_when_no_session(self):
        result = MagicMock()
        result.returncode = 1
        with patch("subprocess.run", return_value=result):
            assert watchdog.bot_is_running() is False


# ── TestKillBot ───────────────────────────────────────────────────────────────

class TestKillBot:
    def test_calls_tmux_kill_session(self):
        with patch("subprocess.run") as mock_run:
            watchdog.kill_bot()
        mock_run.assert_called_once_with(
            ["tmux", "kill-session", "-t", watchdog.BOT_SESSION],
            capture_output=True,
        )


# ── TestStartBot ──────────────────────────────────────────────────────────────

class TestStartBot:
    def test_calls_start_script(self):
        run_result = MagicMock()
        run_result.returncode = 0
        with patch("subprocess.run", return_value=run_result) as mock_run, \
             patch.object(watchdog, "bot_is_running", return_value=True):
            watchdog.start_bot()
        # First call should be to the start script
        first_call = mock_run.call_args_list[0]
        assert str(watchdog.START_SCRIPT) in first_call[0][0]

    def test_returns_true_on_success(self):
        run_result = MagicMock()
        run_result.returncode = 0
        with patch("subprocess.run", return_value=run_result), \
             patch.object(watchdog, "bot_is_running", return_value=True):
            assert watchdog.start_bot() is True

    def test_returns_false_on_timeout(self):
        run_result = MagicMock()
        run_result.returncode = 0
        with patch("subprocess.run", return_value=run_result), \
             patch.object(watchdog, "bot_is_running", return_value=False), \
             patch("time.sleep"):
            assert watchdog.start_bot() is False


# ── TestHandleRestart ─────────────────────────────────────────────────────────

class TestHandleRestart:
    def setup_method(self):
        watchdog._intentionally_stopped = False

    def test_sends_restarting_message_first(self):
        with patch.object(watchdog, "send_telegram") as mock_send, \
             patch.object(watchdog, "kill_bot"), \
             patch.object(watchdog, "start_bot", return_value=True):
            watchdog.handle_restart()
        first_call_text = mock_send.call_args_list[0][0][0]
        assert "Restarting" in first_call_text

    def test_kills_and_starts_bot(self):
        with patch.object(watchdog, "send_telegram"), \
             patch.object(watchdog, "kill_bot") as mock_kill, \
             patch.object(watchdog, "start_bot", return_value=True) as mock_start:
            watchdog.handle_restart()
        mock_kill.assert_called_once()
        mock_start.assert_called_once()

    def test_sends_restarted_message_on_success(self):
        with patch.object(watchdog, "send_telegram") as mock_send, \
             patch.object(watchdog, "kill_bot"), \
             patch.object(watchdog, "start_bot", return_value=True):
            watchdog.handle_restart()
        texts = [c[0][0] for c in mock_send.call_args_list]
        assert any("restarted" in t.lower() or "✅" in t for t in texts)

    def test_sends_failure_message_on_timeout(self):
        with patch.object(watchdog, "send_telegram") as mock_send, \
             patch.object(watchdog, "kill_bot"), \
             patch.object(watchdog, "start_bot", return_value=False):
            watchdog.handle_restart()
        texts = [c[0][0] for c in mock_send.call_args_list]
        assert any("failed" in t.lower() or "❌" in t for t in texts)


# ── TestHandleStop ────────────────────────────────────────────────────────────

class TestHandleStop:
    def setup_method(self):
        watchdog._intentionally_stopped = False

    def test_kills_bot_when_running(self):
        with patch.object(watchdog, "bot_is_running", return_value=True), \
             patch.object(watchdog, "kill_bot") as mock_kill, \
             patch.object(watchdog, "send_telegram"):
            watchdog.handle_stop()
        mock_kill.assert_called_once()

    def test_sends_stopped_message(self):
        with patch.object(watchdog, "bot_is_running", return_value=True), \
             patch.object(watchdog, "kill_bot"), \
             patch.object(watchdog, "send_telegram") as mock_send:
            watchdog.handle_stop()
        texts = [c[0][0] for c in mock_send.call_args_list]
        assert any("stopped" in t.lower() or "🛑" in t for t in texts)

    def test_noop_when_not_running(self):
        with patch.object(watchdog, "bot_is_running", return_value=False), \
             patch.object(watchdog, "kill_bot") as mock_kill, \
             patch.object(watchdog, "send_telegram"):
            watchdog.handle_stop()
        mock_kill.assert_not_called()


# ── TestHandleStart ───────────────────────────────────────────────────────────

class TestHandleStart:
    def setup_method(self):
        watchdog._intentionally_stopped = False

    def test_starts_bot_when_not_running(self):
        with patch.object(watchdog, "bot_is_running", return_value=False), \
             patch.object(watchdog, "start_bot", return_value=True) as mock_start, \
             patch.object(watchdog, "send_telegram"):
            watchdog.handle_start()
        mock_start.assert_called_once()

    def test_sends_started_message(self):
        with patch.object(watchdog, "bot_is_running", return_value=False), \
             patch.object(watchdog, "start_bot", return_value=True), \
             patch.object(watchdog, "send_telegram") as mock_send:
            watchdog.handle_start()
        texts = [c[0][0] for c in mock_send.call_args_list]
        assert any("started" in t.lower() or "✅" in t for t in texts)

    def test_noop_when_already_running(self):
        with patch.object(watchdog, "bot_is_running", return_value=True), \
             patch.object(watchdog, "start_bot") as mock_start, \
             patch.object(watchdog, "send_telegram"):
            watchdog.handle_start()
        mock_start.assert_not_called()


# ── TestHandleStatus ──────────────────────────────────────────────────────────

class TestHandleStatus:
    def test_running_message(self):
        with patch.object(watchdog, "bot_is_running", return_value=True), \
             patch.object(watchdog, "send_telegram") as mock_send:
            watchdog.handle_status()
        text = mock_send.call_args[0][0]
        assert "running" in text.lower() or "✅" in text

    def test_not_running_message(self):
        with patch.object(watchdog, "bot_is_running", return_value=False), \
             patch.object(watchdog, "send_telegram") as mock_send:
            watchdog.handle_status()
        text = mock_send.call_args[0][0]
        assert "not running" in text.lower() or "❌" in text


# ── TestProcessIteration ─────────────────────────────────────────────────────

class TestProcessIteration:
    def setup_method(self):
        watchdog._intentionally_stopped = False

    def test_dispatches_restart(self):
        with patch.object(watchdog, "handle_restart") as mock_h:
            watchdog._process_command("restart")
        mock_h.assert_called_once()

    def test_dispatches_stop(self):
        with patch.object(watchdog, "handle_stop") as mock_h:
            watchdog._process_command("stop")
        mock_h.assert_called_once()

    def test_dispatches_start(self):
        with patch.object(watchdog, "handle_start") as mock_h:
            watchdog._process_command("start")
        mock_h.assert_called_once()

    def test_dispatches_status(self):
        with patch.object(watchdog, "handle_status") as mock_h:
            watchdog._process_command("status")
        mock_h.assert_called_once()

    def test_ignores_unknown(self):
        with patch.object(watchdog, "handle_restart") as mock_r, \
             patch.object(watchdog, "handle_stop") as mock_s, \
             patch.object(watchdog, "handle_start") as mock_st, \
             patch.object(watchdog, "handle_status") as mock_ss:
            watchdog._process_command("foobar")
        mock_r.assert_not_called()
        mock_s.assert_not_called()
        mock_st.assert_not_called()
        mock_ss.assert_not_called()


# ── TestRunLoopStartup ────────────────────────────────────────────────────────

class TestRunLoopStartup:
    def test_sends_startup_notification(self):
        """run_loop() should send a Telegram message when it starts."""
        calls = []

        def fake_select(rlist, wlist, xlist, timeout):
            raise KeyboardInterrupt  # break the loop immediately

        with patch.object(watchdog, "ensure_pipe"), \
             patch.object(watchdog, "send_telegram", side_effect=lambda t: calls.append(t)), \
             patch("os.open", return_value=3), \
             patch("os.close"), \
             patch("select.select", side_effect=fake_select):
            try:
                watchdog.run_loop()
            except KeyboardInterrupt:
                pass

        assert any("👀" in c or "started" in c.lower() for c in calls), \
            f"Expected startup message in send_telegram calls, got: {calls}"
