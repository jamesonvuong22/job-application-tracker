# ApplyTrack — Full-Stack Job Application Tracker

A portfolio project built with **Python, Flask, SQLite, HTML, CSS and JavaScript**. ApplyTrack tracks job applications, follow-ups, interviews, analytics, and CSV imports/exports. **Phase 5 adds account-based data isolation and authentication.**

## Features

- Register, log in and log out; passwords hashed using Werkzeug's secure password hashing.
- Each user's dashboard, deadlines, analytics, CSV imports/exports, and edit/delete routes access **only their own records**.
- CSRF tokens on all state-changing forms and CSRF verification on all POST requests.
- HttpOnly/SameSite=Lax cookies; set `COOKIE_SECURE=1` when using HTTPS.
- Create, update, delete, search and filter applications.
- Record follow-up and interview dates; identify overdue tasks.
- View monthly analytics and status breakdowns.
- Import/export CSV, validate imports, skip per-account duplicates, escape spreadsheet formulas on export.
- Automatic, repeatable migration of Phase 1–4 SQLite databases.

## Install and run locally (Windows PowerShell)

```powershell
cd job-application-tracker
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000 and click **Register**. For a first-time account choose a password with at least 12 characters. To run tests:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

**Important:** run the commands **inside the folder containing `app.py`**, not the outer extracted ZIP folder.

## Upgrade safely from Phase 4

1. Stop your server. Back up your existing `instance/applications.db` or custom `DATABASE` path before changing any code.
2. Copy the updated code and templates into your **existing Git-connected project folder**. **Do not overwrite the existing `instance/` folder or `.git` directory.**
3. Start the server. Database schema migrations automatically add `users` and `applications.user_id`. Existing data is not deleted.
4. **Before exposing the server to anyone**, register your own account **locally**. The **first account created** on a legacy database automatically receives all records that have no `user_id`. This is an intentional migration rule and is unsafe if an untrusted person can register first.
5. Confirm your old records appear, log out and log back in, then run all tests.

If you use a fresh Phase 5 database, each newly registered user starts with an empty list.

## Required before public deployment

This is a learning/portfolio MVP, **not a fully production-hardened service**. Before exposing it publicly, add email verification, password reset, login rate limiting, account recovery, security monitoring, and TLS/HTTPS. Configure a **persistent random `SECRET_KEY`** in the environment (never commit it) and set `COOKIE_SECURE=1` behind HTTPS. The application uses a random process-local secret for local development when `SECRET_KEY` is missing, which logs users out after server restarts. Avoid enabling Flask debugging on public servers.

Generate a secret:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
$env:SECRET_KEY="PASTE_THE_GENERATED_SECRET_HERE"
```

For a hosted service, use a managed secret setting instead of committing `.env`.

## Project files

```text
job-application-tracker/
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── static/
│   ├── app.js
│   └── style.css
├── templates/
│   ├── auth.html         # New registration/login forms
│   ├── base.html         # Account-aware navigation/logout
│   ├── index.html
│   ├── form.html
│   ├── analytics.html
│   └── import_csv.html
└── tests/
    ├── test_app.py
    ├── test_phase2.py
    ├── test_phase3.py
    ├── test_phase4.py
    └── test_phase5.py   # Authentication, CSRF, isolation and migration
```

## GitHub commit

After copying the files and passing tests from inside your existing Git repository:

```powershell
git add .
git commit -m "feat: add authentication and per-user application security"
git push origin main
```

## Next (Phase 6)

Add deployment, automated CI, secret configuration, HTTPS, and production-grade login protections.
