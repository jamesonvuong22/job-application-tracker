# ApplyTrack — Job Application Tracker

A beginner-friendly full-stack web application to organize internship and job applications. Built with **Python, Flask, SQLite, HTML, CSS, and JavaScript**.

## Features (v1)
- Add, edit, and delete job applications
- Track company, role, location, status, date, job posting link, and notes
- Search by company or role and filter by application status
- Dashboard with application counts
- Persistent SQLite database and responsive dark-themed UI
- Basic automated tests

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
- [ ] Follow-up dates and reminders
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
