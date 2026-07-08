import io
import csv
import os
from datetime import date, timedelta

from flask import (Flask, Response, redirect, render_template, request,
                   session, url_for)

import data

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-sumwon-leadership")

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
    focus = [p for p in projects if p["meeting"]]

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
    kpis = {"active": len(focus), "risk": risk, "not_started": not_started,
            "on_track": len(focus) - risk - not_started}

    monday = monday_of_week()
    return render_template(
        "meeting.html", sections=sections, kpis=kpis,
        n_depts=len(sections), n_focus=len(focus),
        meeting_date=monday.strftime("%A, %-d %B %Y"),
        meta=meta, sheet_url=SHEET_URL)


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
                    p["status"], p["progress"], p["deadline"], p["update"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=sumwon-projects.csv"})


@app.route("/refresh")
def refresh():
    data.get_projects(force=True)
    return redirect(request.args.get("next") or request.referrer or url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
