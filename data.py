"""Data layer — reads projects from a Google Sheet (service account) with a
short-lived cache, falling back to bundled demo data when credentials are absent."""
import csv
import json
import os
import time
from datetime import datetime

CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))  # seconds

_cache = {"ts": 0.0, "rows": None, "source": "demo", "error": None, "synced": None}

VALID_STATUSES = ["In Progress", "Completed", "At Risk", "Not Started", "Always On"]

STATUS_CANON = {
    "in progress": "In Progress", "inprogress": "In Progress", "wip": "In Progress",
    "on track": "In Progress", "ontrack": "In Progress",
    "completed": "Completed", "complete": "Completed", "done": "Completed",
    "at risk": "At Risk", "atrisk": "At Risk", "blocked": "At Risk", "off track": "At Risk",
    "not started": "Not Started", "notstarted": "Not Started", "to do": "Not Started", "todo": "Not Started",
    "always on": "Always On", "alwayson": "Always On", "ongoing": "Always On", "bau": "Always On",
}

DEPT_PALETTE = {
    "marketing": "#3B82F6",
    "hr": "#8B5CF6",
    "merch": "#10B981",
    "ai": "#F59E0B",
    "quick wins": "#EC4899",
    "onsite + pricing": "#06B6D4",
    "others": "#7C3AED",
    "finance": "#F97316",
    "new brand launches": "#6366F1",
    "new collaborations": "#A855F7",
    "product": "#14B8A6",
    "wholesale": "#64748B",
    "studio": "#0EA5E9",
    "strategic projects": "#EF4444",
    "corporate & pr": "#84CC16",
}
FALLBACK_COLORS = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EC4899",
                   "#06B6D4", "#7C3AED", "#F97316", "#14B8A6", "#EF4444"]


def dept_color(name, idx=0):
    return DEPT_PALETTE.get((name or "").strip().lower(), FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])


def _from_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    ws_name = os.environ.get("WORKSHEET_NAME", "").strip()
    ws = sh.worksheet(ws_name) if ws_name else sh.sheet1
    return ws.get_all_records()


def _from_csv():
    path = os.path.join(os.path.dirname(__file__), "demo_data.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fmt_deadline(raw):
    if not raw:
        return ""
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, f).strftime("%-d %b %Y")
        except ValueError:
            continue
    return raw


def _norm(rec):
    g = {str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in rec.items()}

    def pick(*names):
        for n in names:
            if g.get(n):
                return g[n]
        return ""

    name = pick("project name", "project", "name", "title")
    if not name:
        return None

    status_raw = pick("status")
    status = STATUS_CANON.get(status_raw.lower(), status_raw.title() if status_raw else "Not Started")
    if status not in VALID_STATUSES:
        status = "In Progress"

    try:
        progress = int(float(pick("progress", "progress %", "%").replace("%", "") or 0))
        progress = max(0, min(100, progress))
    except ValueError:
        progress = 0

    if status == "Completed":
        progress = 100

    meeting = pick("meeting", "monday meeting", "in meeting", "y/n", "yn").lower() in (
        "y", "yes", "true", "1", "\u2713")

    rag = "r" if status == "At Risk" else ("a" if status == "Not Started" else "g")

    return {
        "meeting": meeting,
        "category": pick("category", "department", "dept") or "Uncategorised",
        "sub": pick("sub category", "subcategory", "sub-category", "sub"),
        "name": name,
        "owner": pick("owner", "owners"),
        "ceo_lead": pick("ceo office lead", "ceo lead", "ceo office"),
        "priority": pick("priority").title(),
        "status": status,
        "progress": progress,
        "deadline": _fmt_deadline(pick("deadline", "due date", "due")),
        "update": pick("latest update", "update", "notes", "latest"),
        "rag": rag,
    }


def _meta():
    return {
        "source": _cache["source"],
        "error": _cache["error"],
        "synced": _cache["synced"],
    }


def get_projects(force=False):
    now = time.time()
    if not force and _cache["rows"] is not None and now - _cache["ts"] < CACHE_TTL:
        return _cache["rows"], _meta()

    rows, err, source = None, None, "demo"
    if os.environ.get("GOOGLE_CREDENTIALS_JSON") and os.environ.get("SHEET_ID"):
        try:
            rows = _from_sheet()
            source = "sheet"
        except Exception as e:  # fall back to demo but surface the error
            err = f"{type(e).__name__}: {e}"
            rows = None

    if rows is None:
        rows = _from_csv()

    projects = [p for p in (_norm(r) for r in rows) if p]
    _cache.update(ts=now, rows=projects, source=source, error=err,
                  synced=datetime.now().strftime("%H:%M"))
    return projects, _meta()
