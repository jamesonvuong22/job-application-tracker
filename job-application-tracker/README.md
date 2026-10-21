# ApplyTrack — Job Application Tracker

A beginner-friendly full-stack web application to organize internship and job applications. Built with **Python, Flask, SQLite, HTML, CSS, and JavaScript**.

## Features (v2)
- Add, edit, and delete job applications
- Track company, role, location, status, date, job posting link, and notes
- Search by company or role and filter by application status
- Dashboard with application counts
- Persistent SQLite database and responsive dark-themed UI
- Follow-up deadlines, interview dates, overdue / due-today / upcoming indicators and filters
- Automatic migration of existing v1 SQLite databases (preserves application records)
- Automated tests covering the phase-2 features and migration

## Screenshots
Add screenshots to `docs/` after running the app, then link them here.

## Run locally

Requires **Python 3.10+**.

### Windows (PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

If PowerShell blocks activation, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe app.py` instead.

## Run tests
```bash
python -m pytest -q
```

## Project structure
```text
job-application-tracker/
├── app.py                # Flask routes, validation, SQLite operations
├── templates/
│   ├── base.html         # Shared page layout
│   ├── index.html        # Dashboard, search, filter, list
│   └── form.html         # Create/edit form
├── static/
│   ├── style.css         # Responsive styling
│   └── app.js            # Delete confirmation
├── tests/
│   └── test_app.py       # Basic route and CRUD tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Roadmap
- [x] Dashboard-based follow-up reminders and interview dates
- [ ] Optional email or push notifications (not included in v2)
- [ ] Sortable tables, pagination, and advanced filters
- [ ] Analytics charts (status breakdown and application trends)
- [ ] Export/import CSV
- [ ] Separate backend into routes, models, and services
- [ ] SQLAlchemy + migrations
- [ ] User authentication and account-specific data
- [ ] CSRF protection, stricter validation, and production configuration
- [ ] CI pipeline with GitHub Actions
- [ ] Deploy a public demo with persistent hosted database

## Important security note
This is a **local learning project**, not production-ready software. Flask debug mode is enabled only when running `python app.py`. Do not deploy with debug mode on. Before exposing it publicly, add authentication, CSRF protection, a secure secret key, and deployment configuration. Never commit private application details or local database files.

## License
MIT — see LICENSE.

## Upgrade from v1 to v2
Stop the running server and back up your local `instance/applications.db` file (if present). Replace your **source files** with the updated ones; keep your original `instance/` directory and its database in place. The next app startup automatically adds `follow_up_date` and `interview_date` columns if needed without deleting existing records. Database is local and excluded from Git; do not copy a database from a ZIP on top of your own.

### What counts as overdue?
A follow-up date earlier than your computer's current date, for applications not in Offer, Rejected, or Withdrawn status. A deadline today is "Due today." This is an **in-app** reminder, not an automatic email or notification.


## Phase 3 — Analytics dashboard

Navigate to **Analytics** in the top bar or open `/analytics`. View application counts by month and current status, along with outcome and interview/offer indicators. Select **All time**, **Last 30 days**, or **Last 90 days**. The charts are built with HTML/CSS; no JavaScript chart library or external service is required.

**Interpretation:** The current status is a snapshot, not an event history. The “Outcome recorded” metric is **not** a recruiter-response rate. Interview/offer shares do not represent historical conversion, because previously interviewed applications may now be rejected. A future phase can capture interview events and recruiter replies for more accurate funnel analytics.

This version also fixes the edit-form crash by converting `sqlite3.Row` to a dictionary before rendering. No database migration is required for Phase 3.

Run tests with `python -m pytest -q`. Keep your existing `instance` folder / database when upgrading.
