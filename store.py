"""Meeting store — persists weekly meeting selections and per-project edits
(decision flag, next steps, latest-update override).

Live mode : a dedicated tab in the same Google Sheet (created automatically,
            default name 'DashboardMeetings'). Requires the service account
            to have EDITOR access on the sheet.
Demo mode : a local JSON file (ephemeral — fine for previewing).

The tracker's own department tabs are never written to.
"""
import json
import os
import time
from datetime import datetime

TAB = os.environ.get("MEETING_TAB", "DashboardMeetings")
HEADER = ["Week", "Key", "Category", "Project", "Added", "Decision",
          "Next Steps", "Update Override"]
JSON_PATH = "/tmp/dashboard_meetings.json"

_cache = {"ts": 0.0, "rows": None}
TTL = 30


def _sheet_mode():
    return bool(os.environ.get("GOOGLE_CREDENTIALS_JSON") and os.environ.get("SHEET_ID"))


def _bust():
    _cache["rows"] = None
    _cache["ts"] = 0.0


# ------------------------------------------------------------- sheet backend
def _ws():
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    try:
        ws = sh.worksheet(TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(TAB, rows=2000, cols=len(HEADER))
        ws.append_row(HEADER)
    return ws


def _sheet_rows(force=False):
    now = time.time()
    if not force and _cache["rows"] is not None and now - _cache["ts"] < TTL:
        return _cache["rows"]
    rows = _ws().get_all_values()
    _cache.update(ts=now, rows=rows)
    return rows


# -------------------------------------------------------------- json backend
def _json_load():
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH) as f:
            return json.load(f)
    return {}


def _json_save(d):
    with open(JSON_PATH, "w") as f:
        json.dump(d, f)


# ------------------------------------------------------------------- public
def get_week(week):
    """Return {key: {category, name, decision, next_steps, update_override}}."""
    out = {}
    if _sheet_mode():
        for r in _sheet_rows()[1:]:
            r = r + [""] * (len(HEADER) - len(r))
            if r[0] != week or not r[1]:
                continue
            out[r[1]] = {"category": r[2], "name": r[3],
                         "decision": r[5].strip().upper() in ("Y", "YES", "TRUE", "1"),
                         "next_steps": r[6], "update_override": r[7]}
    else:
        for key, v in _json_load().get(week, {}).items():
            out[key] = v
    return out


def add_items(week, items):
    """items: list of {key, category, name}."""
    if not items:
        return
    existing = get_week(week)
    items = [i for i in items if i["key"] not in existing]
    if not items:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if _sheet_mode():
        rows = [[week, i["key"], i["category"], i["name"], stamp, "", "", ""]
                for i in items]
        _ws().append_rows(rows, value_input_option="RAW")
        _bust()
    else:
        d = _json_load()
        wk = d.setdefault(week, {})
        for i in items:
            wk[i["key"]] = {"category": i["category"], "name": i["name"],
                            "decision": False, "next_steps": "", "update_override": ""}
        _json_save(d)


def remove_item(week, key):
    if _sheet_mode():
        rows = _sheet_rows(force=True)
        for idx, r in enumerate(rows):
            if idx == 0:
                continue
            r = r + [""] * 2
            if r[0] == week and r[1] == key:
                _ws().delete_rows(idx + 1)  # 1-indexed
                _bust()
                return True
        return False
    d = _json_load()
    if key in d.get(week, {}):
        del d[week][key]
        _json_save(d)
        return True
    return False


def save_fields(week, key, decision=None, next_steps=None, update_override=None):
    if _sheet_mode():
        rows = _sheet_rows(force=True)
        for idx, r in enumerate(rows):
            if idx == 0:
                continue
            r = r + [""] * (len(HEADER) - len(r))
            if r[0] == week and r[1] == key:
                ws = _ws()
                rownum = idx + 1
                updates = []
                if decision is not None:
                    updates.append({"range": f"F{rownum}", "values": [["Y" if decision else ""]]})
                if next_steps is not None:
                    updates.append({"range": f"G{rownum}", "values": [[next_steps]]})
                if update_override is not None:
                    updates.append({"range": f"H{rownum}", "values": [[update_override]]})
                if updates:
                    ws.batch_update(updates, value_input_option="RAW")
                _bust()
                return True
        return False
    d = _json_load()
    item = d.get(week, {}).get(key)
    if not item:
        return False
    if decision is not None:
        item["decision"] = bool(decision)
    if next_steps is not None:
        item["next_steps"] = next_steps
    if update_override is not None:
        item["update_override"] = update_override
    _json_save(d)
    return True
