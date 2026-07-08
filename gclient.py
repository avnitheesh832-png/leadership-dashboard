"""Shared Google Sheets client — authenticates once per process and reuses
the connection, instead of re-authenticating on every read/write."""
import json
import os
import threading
import time

_lock = threading.Lock()
_sh = None
_tabs = {"ts": 0.0, "titles": None}
TABS_TTL = 600  # tab list rarely changes — cache for 10 minutes


def spreadsheet():
    """Singleton gspread Spreadsheet handle (thread-safe)."""
    global _sh
    with _lock:
        if _sh is None:
            import gspread
            from google.oauth2.service_account import Credentials
            info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
            creds = Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            _sh = gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"])
        return _sh


def tab_titles(force=False):
    """Cached list of worksheet titles."""
    now = time.time()
    if not force and _tabs["titles"] is not None and now - _tabs["ts"] < TABS_TTL:
        return _tabs["titles"]
    titles = [ws.title for ws in spreadsheet().worksheets()]
    _tabs.update(ts=now, titles=titles)
    return titles
