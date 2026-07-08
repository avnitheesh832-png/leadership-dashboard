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

## 1. The Google Sheet

Create a Google Sheet with these exact headers in row 1 (or import
`demo_data.csv` via File → Import as a starting template):

| Meeting | Category | Sub Category | Project Name | Owner | CEO Office Lead | Priority | Status | Progress | Deadline | Latest Update |
|---------|----------|--------------|--------------|-------|-----------------|----------|--------|----------|----------|---------------|

Column rules:
- **Meeting** — `Y` includes the project in the Monday Meeting view, `N` (or blank) keeps it in the projects list only
- **Priority** — High / Medium / Low (or blank)
- **Status** — In Progress, Completed, At Risk, Not Started, Always On
  (variants like "Blocked", "Done", "WIP", "Ongoing" are auto-mapped)
- **Progress** — number 0–100 (Completed auto-shows 100)
- **Deadline** — any of YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY

## 2. Google Cloud service account (one-time, ~5 minutes)

1. Go to https://console.cloud.google.com → create (or pick) a project
2. **APIs & Services → Library** → search **Google Sheets API** → Enable
3. **APIs & Services → Credentials → Create Credentials → Service account**
   (any name, e.g. `leadership-dashboard`) → Done
4. Open the service account → **Keys → Add key → Create new key → JSON** →
   a JSON file downloads. Keep it private.
5. Copy the service account's email (looks like
   `leadership-dashboard@project-id.iam.gserviceaccount.com`) and **share your
   Google Sheet with that email as Viewer**.

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

1. Team updates the Google Sheet during the week (status, progress, latest update)
2. Flag `Meeting = Y` on the projects to discuss on Monday
3. Open `/meeting` in the CEO session — Present for fullscreen, Export PDF to archive the week
