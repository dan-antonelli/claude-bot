import os

# Must be set before bot.py is imported (module-level env reads)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "111111111:test_token_for_pytest")
os.environ.setdefault("TELEGRAM_CHAT_ID", "999")
os.environ["WATCHDOG_PIPE"] = "/tmp/test-claude-bot.fifo"
