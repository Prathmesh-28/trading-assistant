"""Shared test setup.

Two jobs, both of which must happen before any project module is imported:

1. Put the repo root on sys.path so `import costs` / `import server` work
   no matter how pytest was invoked (`pytest tests/` from anywhere).
2. Pin the environment to hermetic offline values. config.py's load_dotenv()
   never overrides variables that are already set, so exporting them here
   guarantees synthetic mode (no Groww, no Telegram, no network) and a
   throwaway journal, even if a developer has a real .env in the repo.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ["GROWW_API_KEY"] = ""
os.environ["GROWW_API_SECRET"] = ""
os.environ["GROWW_TOTP_SECRET"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["JOURNAL_PATH"] = "/tmp/test_auth_ci.db"
os.environ["AUTH_USERNAME"] = "u"
os.environ["AUTH_PASSWORD"] = "p"
os.environ["LIVE"] = "false"
