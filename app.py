import io
import csv
import os
from datetime import date, timedelta

from flask import (Flask, Response, redirect, render_template, request,
                   session, url_for)

import data
import store

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-sumwon-leadership")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600  # cache static assets 1h

try:
    from flask_compress import Compress
    Compress(app)  # gzip/brotli responses (the projects table shrinks ~10x)
except ImportError:
    pass

PIN = os.environ.get("DASHBOARD_PIN", "2026")
SHEET_URL = os.environ.get("SHEET_URL", "")


# ---------------------------------------------------------------- auth gate
@app.before_request
def gate():
    if request.endpoint in ("login", "static") or request.path.startswith("/static"):
        return None
    if not session.get("authed"):
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("pin", "").strip() == PIN:
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("home"))
        error = "Incorrect PIN — try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- helpers
def dept_summary(projects):
    order, counts = [], {}
    for p in projects:
        c = p["category"]
        if c not in counts:
            counts[c] = 0
            order.append(c)
        counts[c] += 1
    depts = [{"name": c, "count": counts[c], "color": data.dept_color(c, i)}
             for i, c in enumerate(order)]
    depts.sort(key=lambda d: -d["count"])
    return depts


def status_counts(projects):
    keys = ["In Progress", "Completed", "At Risk", "Not Started", "Always On"]
    out = {k: 0 for k in keys}
    for p in projects:
        out[p["status"]] = out.get(p["status"], 0) + 1
    out["Total"] = len(projects)
    return out


def monday_of_week():
    today = date.today()
    return today - timedelta(days=today.weekday())


# ---------------------------------------------------------------- routes
@app.route("/")
def home():
    projects, meta = data.get_projects()
    return render_template("home.html", depts=dept_summary(projects),
                           total=len(projects), meta=meta, sheet_url=SHEET_URL)


@app.route("/projects")
def projects_page():
    projects, meta = data.get_projects()
    depts = dept_summary(projects)
    owners = sorted({p["owner"] for p in projects if p["owner"]})
    priorities = [pr for pr in ["High", "Medium", "Low"]
                  if any(p["priority"] == pr for p in projects)]
    return render_template(
        "projects.html", projects=projects, depts=depts, owners=owners,
        priorities=priorities, counts=status_counts(projects),
        active_dept=request.args.get("dept", ""), meta=meta, sheet_url=SHEET_URL)


@app.route("/meeting")
def meeting():
    projects, meta = data.get_projects()
    week = monday_of_week().isoformat()
    sel = store.get_week(week)

    by_key = {p["category"] + "||" + p["name"]: p for p in projects}
    focus = []
    for key, s in sel.items():
        p = by_key.get(key)
        if p:
            q = dict(p)
        else:  # project no longer in the tracker — keep the stored shell
            q = {"category": s["category"], "name": s["name"], "sub": "",
                 "owner": "", "priority": "", "status": "Not Started",
                 "progress": 0, "deadline": "", "latest_update": "", "update_label": "",
                 "details": "", "doc": "", "rag": "a", "missing": True, "latest_update": ""}
        q["key"] = key
        q["decision"] = s["decision"]
        q["next_steps"] = s["next_steps"]
        q["update_override"] = s["update_override"]
        if s["update_override"]:
            q["latest_update"] = s["update_override"]
            q["update_label"] = "EDITED"
        focus.append(q)

    order, groups = [], {}
    for p in focus:
        c = p["category"]
        if c not in groups:
            groups[c] = []
            order.append(c)
        groups[c].append(p)
    sections = [{"name": c, "color": data.dept_color(c, i), "projects": groups[c]}
                for i, c in enumerate(order)]

    risk = sum(1 for p in focus if p["status"] == "At Risk")
    not_started = sum(1 for p in focus if p["status"] == "Not Started")
    decisions = sum(1 for p in focus if p["decision"])
    kpis = {"active": len(focus), "risk": risk, "not_started": not_started,
            "on_track": len(focus) - risk - not_started, "decisions": decisions}

    available = []
    for p in projects:
        key = p["category"] + "||" + p["name"]
        if key not in sel:
            available.append({"key": key, "category": p["category"],
                              "name": p["name"], "owner": p["owner"],
                              "status": p["status"], "progress": p["progress"],
                              "priority": p["priority"]})

    monday = monday_of_week()
    dept_names = sorted({p["category"] for p in projects})
    return render_template(
        "meeting.html", sections=sections, kpis=kpis, available=available,
        dept_names=dept_names,
        n_depts=len(sections), n_focus=len(focus), week=week,
        meeting_date=monday.strftime("%A, %-d %B %Y"),
        meta=meta, sheet_url=SHEET_URL)


# ------------------------------------------------------------- meeting APIs
@app.route("/api/meeting/add", methods=["POST"])
def api_meeting_add():
    body = request.get_json(silent=True) or {}
    items = body.get("items", [])
    clean = [{"key": str(i.get("key", ""))[:300],
              "category": str(i.get("category", ""))[:100],
              "name": str(i.get("name", ""))[:200]}
             for i in items if i.get("key")]
    store.add_items(monday_of_week().isoformat(), clean)
    return {"ok": True, "added": len(clean)}


@app.route("/api/meeting/remove", methods=["POST"])
def api_meeting_remove():
    body = request.get_json(silent=True) or {}
    ok = store.remove_item(monday_of_week().isoformat(), str(body.get("key", "")))
    return {"ok": bool(ok)}


@app.route("/api/meeting/clear", methods=["POST"])
def api_meeting_clear():
    removed = store.clear_week(monday_of_week().isoformat())
    return {"ok": True, "removed": removed}


@app.route("/api/meeting/save", methods=["POST"])
def api_meeting_save():
    body = request.get_json(silent=True) or {}
    key = str(body.get("key", ""))
    kwargs = {}
    if "decision" in body:
        kwargs["decision"] = bool(body["decision"])
    if "next_steps" in body:
        kwargs["next_steps"] = str(body["next_steps"])[:2000]
    if "update_override" in body:
        kwargs["update_override"] = str(body["update_override"])[:2000]
    ok = store.save_fields(monday_of_week().isoformat(), key, **kwargs)
    return {"ok": bool(ok)}


@app.route("/export.csv")
def export_csv():
    projects, _ = data.get_projects()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Meeting", "Category", "Sub Category", "Project Name", "Owner",
                "CEO Office Lead", "Priority", "Status", "Progress", "Deadline",
                "Latest Update"])
    for p in projects:
        w.writerow(["Y" if p["meeting"] else "N", p["category"], p["sub"],
                    p["name"], p["owner"], p["ceo_lead"], p["priority"],
                    p["status"], p["progress"], p["deadline"], p["latest_update"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=sumwon-projects.csv"})


@app.route("/refresh")
def refresh():
    data.get_projects(force=True)
    return redirect(request.args.get("next") or request.referrer or url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
