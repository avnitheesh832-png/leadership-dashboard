# Sumwon Studios — Leadership Dashboard

Weekly CEO/leadership project dashboard. One Google Sheet is the single source
of truth; edits in the sheet reflect on the dashboard live (60-second cache,
or instantly via the Refresh button).

**Pages**
- `/` — Home: departments overview
- `/projects` — Full projects table with sidebar, KPIs, search and filters
- `/meeting` — Monday Meeting view (projects where `Meeting = Y`), with
  Cards/List toggle, CEO Lead filter, dark mode, Present (fullscreen),
  Email summary and Export PDF (print)
- `/export.csv` — Excel/CSV download

The app runs in **demo mode** (bundled sample data) until Google Sheet
credentials are configured — so you can deploy and review immediately.

---

## 1. The Google Sheet — works with the existing tracker as-is

The app is built for the **"Projects Tracker - CEO - COO - CBO Office"** sheet
structure and needs **no restructuring**:

- **Every tab = a department** (Merch, Marketing, AI, Finance, Legal, Quick Wins...).
  Dashboard/utility tabs (names containing *dashboard, view, notes, old*) are
  skipped automatically. Override with `INCLUDE_TABS` or `EXCLUDE_TABS`
  (comma-separated tab names) if needed.
- The **header row is auto-detected** (the row containing `Project Name`), so the
  title and quick-glance counters above it are ignored.
- Pre-numbered **empty rows are skipped**.
- Recognised columns: `Subject`, `Project Name`, `Details & Comments`,
  `Link to Document`, `Priority` ("High Priority" etc.), `Owner`, `Deadline`
  (any common format, free text like "August" passes through), `Status`,
  `% Done`, `Additional Comments`, and any number of dated `Update DD.MM`
  columns — the **right-most non-empty update** is shown as Latest Update.
- **Monday Meeting selection:** the meeting is curated inside the dashboard.
  Click **+ ADD PROJECT** on the meeting page to pull any existing tracker
  project into this week's agenda (search, add one by one, or "Add all
  active"). Each card then has an editable **Latest Update**, a **Next
  Steps** box, a **Decision Required** toggle, and a remove (×) button.
  Everything auto-saves to a dedicated `DashboardMeetings` tab the app
  creates in your sheet — one row per project per week, fully auditable,
  and your tracker tabs are never modified.

## 2. Google Cloud service account (one-time, ~5 minutes)

1. Go to https://console.cloud.google.com → create (or pick) a project
2. **APIs & Services → Library** → search **Google Sheets API** → Enable
3. **APIs & Services → Credentials → Create Credentials → Service account**
   (any name, e.g. `leadership-dashboard`) → Done
4. Open the service account → **Keys → Add key → Create new key → JSON** →
   a JSON file downloads. Keep it private.
5. Copy the service account's email (looks like
   `leadership-dashboard@project-id.iam.gserviceaccount.com`) and **share your
   Google Sheet with that email as EDITOR** (the dashboard writes meeting
   selections and edits to its own 'DashboardMeetings' tab — it never touches
   the tracker's department tabs).

## 3. Deploy on Railway

1. Push this folder to a **private** GitHub repo (or use `railway init` + `railway up` with the CLI)
2. In Railway: **New Project → Deploy from GitHub repo**
3. In the service → **Variables**, add:

| Variable | Value |
|----------|-------|
| `GOOGLE_CREDENTIALS_JSON` | Paste the **entire contents** of the downloaded JSON key file |
| `SHEET_ID` | From the sheet URL: `docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit` |
| `SHEET_URL` | (optional) Full sheet URL — powers the "Sheets" / "Add in Sheet" buttons |
| `WORKSHEET_NAME` | (optional) Tab name if not the first tab |
| `DASHBOARD_PIN` | Access PIN (default `2026` — change it) |
| `SECRET_KEY` | Any long random string (session security) |
| `CACHE_TTL` | (optional) Seconds between sheet re-reads, default `60` |
| `MEETING_TAB` | (optional) Name of the tab the app stores meeting data in, default `DashboardMeetings` |

4. Railway detects the Procfile and deploys. Open the generated domain,
   enter the PIN, done.

The footer/top bar shows **LIVE · GOOGLE SHEET** when connected, or
**DEMO DATA** when running on the bundled sample.

## 4. Run locally (optional)

```bash
pip install -r requirements.txt
python app.py            # demo mode on http://localhost:5000  (PIN 2026)
```

## Weekly workflow

1. Team updates the tracker during the week (status, progress, updates)
2. Before Monday: open `/meeting`, click **+ ADD PROJECT** and build the agenda;
   type updates/next steps and tick Decision Required where needed
3. In the CEO session — Present for fullscreen, Export PDF to archive the week
4. Next Monday starts with a fresh empty agenda (each week is stored separately)
