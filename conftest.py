import os

# Override env vars unconditionally so shell-level values don't pollute tests.
os.environ["TELEGRAM_BOT_TOKEN"] = "111111111:test_token_for_pytest"
os.environ["TELEGRAM_CHAT_ID"] = "999"
