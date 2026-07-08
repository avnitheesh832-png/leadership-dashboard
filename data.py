"""Data layer — reads the Sumwon 'Projects Tracker - CEO - COO - CBO Office'
Google Sheet (service account), one department per tab, with a short cache.
Falls back to bundled demo data when credentials are absent.

Sheet handling:
- Every tab is treated as a department, except dashboard/utility tabs
  (names containing 'dashboard', 'view', 'notes', 'old' — configurable via
  INCLUDE_TABS / EXCLUDE_TABS env vars).
- The header row is auto-detected (the row containing 'Project Name'),
  so the title/KPI block at the top of each tab is ignored.
- Rows without a Project Name are skipped (pre-numbered empty rows).
- 'Latest update' = right-most non-empty 'Update DD.MM' column,
  falling back to Additional Comments.
- Meeting flag: if a 'Meeting' column exists (Y/N) it is used; otherwise
  every non-Completed project is included in the Monday Meeting view.
"""
import csv
import json
import os
import re
import threading
import time
from datetime import datetime

CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))  # seconds

_cache = {"ts": 0.0, "rows": None, "source": "demo", "error": None, "synced": None}

VALID_STATUSES = ["In Progress", "Completed", "At Risk", "Not Started", "Always On"]

STATUS_CANON = {
    "in progress": "In Progress", "inprogress": "In Progress", "wip": "In Progress",
    "on track": "In Progress", "ontrack": "In Progress", "active": "In Progress",
    "completed": "Completed", "complete": "Completed", "done": "Completed", "closed": "Completed",
    "at risk": "At Risk", "atrisk": "At Risk", "blocked": "At Risk", "off track": "At Risk",
    "not started": "Not Started", "notstarted": "Not Started", "to do": "Not Started",
    "todo": "Not Started", "on hold": "Not Started", "paused": "Not Started",
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
    "commercial finance": "#FB7185",
    "new brand launches": "#6366F1",
    "new collaborations": "#A855F7",
    "new channels": "#22C55E",
    "product": "#14B8A6",
    "wholesale": "#64748B",
    "studio": "#0EA5E9",
    "strategic projects": "#EF4444",
    "corporate & pr": "#84CC16",
    "legal": "#78716C",
}
FALLBACK_COLORS = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EC4899",
                   "#06B6D4", "#7C3AED", "#F97316", "#14B8A6", "#EF4444"]

# Tabs skipped by default (dashboards / views / scratch tabs inside the sheet)
DEFAULT_EXCLUDE_PATTERN = re.compile(r"dashboard|view|notes|old", re.I)

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y")

MEETING_YES = ("y", "yes", "true", "1", "\u2713")


def dept_color(name, idx=0):
    return DEPT_PALETTE.get((name or "").strip().lower(), FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])


def _fmt_deadline(raw):
    if not raw:
        return ""
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(raw, f).strftime("%-d %b %Y")
        except ValueError:
            continue
    return raw  # free text like "August" passes through


def _canon_status(raw):
    if not raw:
        return "Not Started"
    s = STATUS_CANON.get(raw.strip().lower())
    if s:
        return s
    t = raw.strip().title()
    return t if t in VALID_STATUSES else "In Progress"


def _canon_priority(raw):
    p = re.sub(r"priority", "", raw or "", flags=re.I).strip().title()
    return p if p in ("High", "Medium", "Low") else (p or "")


def _pct(raw):
    try:
        v = int(float(str(raw).replace("%", "").strip() or 0))
        return max(0, min(100, v))
    except ValueError:
        return 0


def _make_project(category, name, sub, owner, priority, status, progress,
                  deadline, update, update_label, details, doc, meeting):
    status = _canon_status(status)
    progress = 100 if status == "Completed" else _pct(progress)
    rag = "r" if status == "At Risk" else ("a" if status == "Not Started" else "g")
    return {
        "meeting": meeting if meeting is not None else (status != "Completed"),
        "category": category or "Uncategorised",
        "sub": sub or "",
        "name": name,
        "owner": owner or "",
        "ceo_lead": "",
        "priority": _canon_priority(priority),
        "status": status,
        "progress": progress,
        "deadline": _fmt_deadline(deadline or ""),
        "latest_update": update or "",
        "update_label": update_label or "",
        "details": details or "",
        "doc": doc or "",
        "rag": rag,
    }


# ------------------------------------------------------------------ sheet
def _selected_tabs(all_titles):
    include = [t.strip() for t in os.environ.get("INCLUDE_TABS", "").split(",") if t.strip()]
    if include:
        return [t for t in all_titles if t in include]
    exclude = {t.strip().lower() for t in os.environ.get("EXCLUDE_TABS", "").split(",") if t.strip()}
    out = []
    for t in all_titles:
        if t.lower() in exclude:
            continue
        if not exclude and DEFAULT_EXCLUDE_PATTERN.search(t):
            continue
        out.append(t)
    return out


def _parse_tab(title, rows):
    """Parse one department tab: locate the header row, map columns, emit projects."""
    hdr_idx, headers = None, []
    for i, row in enumerate(rows[:40]):
        low = [str(c).strip().lower() for c in row]
        if "project name" in low:
            hdr_idx, headers = i, low
            break
    if hdr_idx is None:
        return []

    def col(*names, prefix=False):
        for n in names:
            for j, h in enumerate(headers):
                if (prefix and h.startswith(n)) or (not prefix and h == n):
                    return j
        return None

    c_name = col("project name")
    c_subj = col("subject", "sub category", "subcategory")
    c_details = col("details & comments", "details", "description")
    c_doc = col("link to document", "link", "document")
    c_pri = col("priority")
    c_owner = col("owner", "owners")
    c_dl = col("deadline", "due date", "due")
    c_status = col("status")
    c_prog = col("% done", "progress", "% complete", "percent")
    c_add = col("additional comments", "comments")
    c_meet = col("meeting", "monday meeting", "y/n")
    upd_cols = [(j, headers[j]) for j in range(len(headers)) if headers[j].startswith("update")]

    out = []
    for row in rows[hdr_idx + 1:]:
        def get(j):
            return str(row[j]).strip() if j is not None and j < len(row) else ""

        name = get(c_name)
        if not name:
            continue

        update, update_label = "", ""
        for j, h in upd_cols:  # right-most non-empty dated update wins
            v = get(j)
            if v:
                update = v
                update_label = re.sub(r"^update", "", h, flags=re.I).strip(" .:—-")
        if not update:
            update = get(c_add)

        meeting = None
        if c_meet is not None:
            meeting = get(c_meet).lower() in MEETING_YES

        sub = get(c_subj)
        if sub.lower() == title.strip().lower():
            sub = ""

        out.append(_make_project(
            category=title.strip(), name=name, sub=sub, owner=get(c_owner),
            priority=get(c_pri), status=get(c_status), progress=get(c_prog),
            deadline=get(c_dl), update=update, update_label=update_label,
            details=get(c_details), doc=get(c_doc), meeting=meeting))
    return out


def _from_sheet():
    import gclient
    sh = gclient.spreadsheet()
    tabs = _selected_tabs(gclient.tab_titles())
    if not tabs:
        return []

    ranges = ["'{}'!A1:Z500".format(t.replace("'", "''")) for t in tabs]
    resp = sh.values_batch_get(ranges)
    projects = []
    for title, vr in zip(tabs, resp.get("valueRanges", [])):
        projects.extend(_parse_tab(title, vr.get("values", [])))
    return projects


# ------------------------------------------------------------------ demo csv
def _from_csv():
    path = os.path.join(os.path.dirname(__file__), "demo_data.csv")
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
            if not g.get("project name"):
                continue
            out.append(_make_project(
                category=g.get("category", ""), name=g["project name"],
                sub=g.get("sub category", ""), owner=g.get("owner", ""),
                priority=g.get("priority", ""), status=g.get("status", ""),
                progress=g.get("progress", ""), deadline=g.get("deadline", ""),
                update=g.get("latest update", ""), update_label="",
                details="", doc="",
                meeting=g.get("meeting", "").lower() in MEETING_YES))
            out[-1]["ceo_lead"] = g.get("ceo office lead", "")
    return out


# ------------------------------------------------------------------ cache
def _meta():
    return {"source": _cache["source"], "error": _cache["error"], "synced": _cache["synced"]}


_refresh_lock = threading.Lock()


def _load():
    rows, err, source = None, None, "demo"
    if os.environ.get("GOOGLE_CREDENTIALS_JSON") and os.environ.get("SHEET_ID"):
        try:
            rows = _from_sheet()
            source = "sheet"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            rows = None
    if rows is None:
        rows = _from_csv()
    _cache.update(ts=time.time(), rows=rows, source=source, error=err,
                  synced=datetime.now().strftime("%H:%M"))


def _load_bg():
    if _refresh_lock.acquire(blocking=False):
        try:
            _load()
        except Exception:
            pass
        finally:
            _refresh_lock.release()


def get_projects(force=False):
    """Stale-while-revalidate: pages always render instantly from cache;
    a background thread refreshes from the sheet when the cache is stale.
    force=True (the Refresh button) reloads synchronously."""
    if _cache["rows"] is None or force:
        with _refresh_lock:
            if _cache["rows"] is None or force:
                _load()
        return _cache["rows"], _meta()

    if time.time() - _cache["ts"] >= CACHE_TTL:
        threading.Thread(target=_load_bg, daemon=True).start()

    return _cache["rows"], _meta()
