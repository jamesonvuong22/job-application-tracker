import os
import csv
import io
import sqlite3
import secrets
import hmac
import functools
from flask import session, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, abort, flash, redirect, render_template, request, url_for, Response

STATUSES = ('Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected', 'Withdrawn')
CSV_FIELDS = ('company', 'position', 'location', 'status', 'applied_date', 'job_url', 'notes', 'follow_up_date', 'interview_date')
CSV_LIMIT_BYTES = 2 * 1024 * 1024
CSV_MAX_ROWS = 5000


def safe_csv_cell(value):
    """Prevent formula execution when the CSV is opened in spreadsheet software."""
    value = str(value or '')
    if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value


def validate_csv_row(data):
    if not data['company'] or not data['position']:
        return 'company and position are required'
    if data['status'] not in STATUSES:
        return 'invalid status'
    for name in ('applied_date', 'follow_up_date', 'interview_date'):
        if name == 'applied_date' or data[name]:
            try:
                date.fromisoformat(data[name])
            except ValueError:
                return f'invalid {name}'
    if data['job_url'] and not data['job_url'].startswith(('https://', 'http://')):
        return 'invalid job_url'
    for field, length in (('company', 120), ('position', 160), ('location', 160), ('job_url', 2000)):
        if len(data[field]) > length:
            return f'{field} exceeds {length} characters'
    return None



def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32), DATABASE=os.environ.get('DATABASE', str(Path(app.instance_path) / 'applications.db')))
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1', MAX_CONTENT_LENGTH=3 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)

    def connect():
        db = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        return db

    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Applied',
            applied_date TEXT NOT NULL,
            job_url TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')

    # Safe, repeatable migration of existing version-1 databases.
    with connect() as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(applications)')}
        for column in ('follow_up_date', 'interview_date'):
            if column not in columns:
                db.execute(f"ALTER TABLE applications ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

    # Phase 5: user accounts. Older databases are upgraded without dropping applications.
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(applications)')}
        if 'user_id' not in columns:
            db.execute('ALTER TABLE applications ADD COLUMN user_id INTEGER REFERENCES users(id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_applications_owner ON applications(user_id)')

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        if session.get('user_id'):
            with connect() as db:
                g.user = db.execute('SELECT id, email FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if g.user is None:
                session.clear()
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected = session.get('csrf_token', '')
            provided = request.form.get('csrf_token', '') or request.headers.get('X-CSRF-Token', '')
            if not expected or not hmac.compare_digest(expected, provided):
                abort(400, description='Invalid or missing CSRF token.')

    @app.context_processor
    def inject_auth():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return {'current_user': g.get('user'), 'csrf_token': session['csrf_token']}

    def login_required(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if g.user:
            return redirect(url_for('index'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            if len(email) > 254 or '@' not in email or email.startswith('@') or '.' not in email.rsplit('@', 1)[-1]:
                flash('Enter a valid email address.', 'error')
                return render_template('auth.html', mode='register'), 400
            if len(password) < 12 or len(password) > 256:
                flash('Password must be 12–256 characters.', 'error')
                return render_template('auth.html', mode='register'), 400
            try:
                with connect() as db:
                    first_user = db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
                    cursor = db.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)',
                                        (email, generate_password_hash(password)))
                    user_id = cursor.lastrowid
                    # For existing local Phase 1-4 databases only: first registrant inherits
                    # legacy unowned records. Register locally before exposing the app online.
                    if first_user:
                        db.execute('UPDATE applications SET user_id = ? WHERE user_id IS NULL', (user_id,))
            except sqlite3.IntegrityError:
                flash('An account with this email already exists.', 'error')
                return render_template('auth.html', mode='register'), 400
            session.clear()
            session['user_id'] = user_id
            session['csrf_token'] = secrets.token_urlsafe(32)
            flash('Account created.', 'success')
            return redirect(url_for('index'))
        return render_template('auth.html', mode='register')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if g.user:
            return redirect(url_for('index'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            with connect() as db:
                account = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if account is None or not check_password_hash(account['password_hash'], password):
                flash('Invalid email or password.', 'error')
                return render_template('auth.html', mode='login'), 401
            session.clear()
            session['user_id'] = account['id']
            session['csrf_token'] = secrets.token_urlsafe(32)
            return redirect(url_for('index'))
        return render_template('auth.html', mode='login')

    @app.post('/logout')
    @login_required
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @login_required
    def index():
        search = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        deadline_filter = request.args.get('deadline', '').strip()
        today = date.today().isoformat()
        sql = 'SELECT * FROM applications WHERE user_id = ?'
        args = [g.user['id']]
        if search:
            sql += ' AND (company LIKE ? OR position LIKE ?)'
            args.extend([f'%{search}%', f'%{search}%'])
        if status in STATUSES:
            sql += ' AND status = ?'
            args.append(status)
        if deadline_filter == 'overdue':
            sql += " AND follow_up_date != '' AND follow_up_date < ? AND status NOT IN ('Offer','Rejected','Withdrawn')"
            args.append(today)
        elif deadline_filter == 'today':
            sql += " AND follow_up_date = ? AND status NOT IN ('Offer','Rejected','Withdrawn')"
            args.append(today)
        elif deadline_filter == 'upcoming':
            sql += " AND follow_up_date > ? AND status NOT IN ('Offer','Rejected','Withdrawn')"
            args.append(today)
        sql += " ORDER BY CASE WHEN follow_up_date != '' THEN 0 ELSE 1 END, follow_up_date ASC, applied_date DESC, id DESC"
        with connect() as db:
            applications = db.execute(sql, args).fetchall()
            counts = {row['status']: row['total'] for row in db.execute('SELECT status, COUNT(*) AS total FROM applications WHERE user_id = ? GROUP BY status', (g.user['id'],))}
            deadline_counts = dict(db.execute("""SELECT
                SUM(CASE WHEN follow_up_date != '' AND follow_up_date < ? THEN 1 ELSE 0 END) AS overdue,
                SUM(CASE WHEN follow_up_date = ? THEN 1 ELSE 0 END) AS today,
                SUM(CASE WHEN follow_up_date > ? THEN 1 ELSE 0 END) AS upcoming
                FROM applications WHERE user_id = ? AND status NOT IN ('Offer','Rejected','Withdrawn')""", (today, today, today, g.user['id'])).fetchone())
        return render_template('index.html', applications=applications, counts=counts, statuses=STATUSES, search=search, selected_status=status, deadline_filter=deadline_filter, deadline_counts=deadline_counts, today=today)


    @app.get('/analytics')
    @login_required
    def analytics():
        """Aggregate actual application records without storing duplicate analytics data."""
        period = request.args.get('period', 'all')
        if period not in ('all', '30', '90'):
            period = 'all'
        where = ' WHERE user_id = ?'
        params = (g.user['id'],)
        if period != 'all':
            # Inclusive calendar window: today plus the previous N-1 days.
            start = (date.today() - timedelta(days=int(period) - 1)).isoformat()
            where += ' AND applied_date >= ? AND applied_date <= ?'
            params = (g.user['id'], start, date.today().isoformat())
        with connect() as db:
            total = db.execute('SELECT COUNT(*) FROM applications' + where, params).fetchone()[0]
            status_rows = db.execute('SELECT status, COUNT(*) AS total FROM applications' + where + ' GROUP BY status', params).fetchall()
            month_rows = db.execute("SELECT substr(applied_date, 1, 7) AS month, COUNT(*) AS total FROM applications" + where + ' GROUP BY month ORDER BY month', params).fetchall()
        status_counts = {status: 0 for status in STATUSES}
        for r in status_rows:
            status_counts[r['status']] = r['total']
        # These are CURRENT pipeline-status ratios, not lifetime historical conversion rates.
        responded = sum(status_counts.get(s, 0) for s in ('Interview', 'Offer', 'Rejected'))
        interview_or_offer = sum(status_counts.get(s, 0) for s in ('Interview', 'Offer'))
        offers = status_counts.get('Offer', 0)
        # A rejected application may or may not have received a personal response.
        # Label this an "outcome recorded" proxy rather than a recruiter response rate.
        outcome_recorded = responded
        metrics = {
            'total': total,
            'interview_or_offer': interview_or_offer,
            'offers': offers,
            'outcome_pct': round(100 * outcome_recorded / total, 1) if total else 0,
            'interview_pct': round(100 * interview_or_offer / total, 1) if total else 0,
            'offer_pct': round(100 * offers / total, 1) if total else 0,
        }
        months = [{'label': row['month'], 'total': row['total']} for row in month_rows]
        max_month = max((row['total'] for row in months), default=0)
        for row in months:
            row['width'] = round(100 * row['total'] / max_month, 1) if max_month else 0
        breakdown = [{'status': status, 'total': count,
                      'pct': round(100 * count / total, 1) if total else 0}
                     for status, count in status_counts.items()]
        return render_template('analytics.html', period=period, metrics=metrics,
                               months=months, breakdown=breakdown)

    @app.get('/export/csv')
    @login_required
    def export_csv():
        """Export all records in a spreadsheet-compatible file (no database IDs)."""
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(CSV_FIELDS)
        with connect() as db:
            for record in db.execute('SELECT * FROM applications WHERE user_id = ? ORDER BY applied_date DESC, id DESC', (g.user['id'],)):
                writer.writerow([safe_csv_cell(record[field]) for field in CSV_FIELDS])
        return Response('\ufeff' + output.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': 'attachment; filename="applytrack-applications.csv"',
            'Cache-Control': 'no-store',
        })

    @app.route('/import/csv', methods=['GET', 'POST'])
    @login_required
    def import_csv():
        if request.method == 'GET':
            return render_template('import_csv.html', fields=CSV_FIELDS)
        upload = request.files.get('file')
        if not upload or not upload.filename or not upload.filename.lower().endswith('.csv'):
            flash('Choose a .csv file to import.', 'error')
            return redirect(url_for('import_csv'))
        raw = upload.stream.read(CSV_LIMIT_BYTES + 1)
        if len(raw) > CSV_LIMIT_BYTES:
            flash('CSV exceeds the 2 MB limit.', 'error')
            return redirect(url_for('import_csv'))
        try:
            content = raw.decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content, newline=''), strict=True)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError('Missing or repeated header columns.')
            if any(field not in reader.fieldnames for field in ('company', 'position', 'applied_date')):
                raise ValueError('CSV must have company, position, and applied_date columns.')
            if any(field not in CSV_FIELDS for field in reader.fieldnames):
                raise ValueError('CSV contains unsupported columns.')
            rows = []
            for line, row in enumerate(reader, start=2):
                if len(rows) >= CSV_MAX_ROWS:
                    raise ValueError('CSV exceeds the 5,000-row limit.')
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f'Row {line}: incorrect number of fields.')
                data = {field: (row.get(field) or '').strip() for field in CSV_FIELDS}
                data['status'] = data['status'] or 'Applied'
                error = validate_csv_row(data)
                if error:
                    raise ValueError(f'Row {line}: {error}.')
                rows.append(data)
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            flash(f'Import cancelled: {exc} No applications were added.', 'error')
            return redirect(url_for('import_csv'))
        inserted = skipped = 0
        # One transaction; duplicates are matched by company, position, and application date.
        with connect() as db:
            existing = {(r['company'].casefold(), r['position'].casefold(), r['applied_date'])
                        for r in db.execute('SELECT company, position, applied_date FROM applications WHERE user_id = ?', (g.user['id'],))}
            for data in rows:
                key = (data['company'].casefold(), data['position'].casefold(), data['applied_date'])
                if key in existing:
                    skipped += 1
                    continue
                db.execute('INSERT INTO applications (user_id, ' + ', '.join(CSV_FIELDS) + ') VALUES (:user_id, ' +
                           ', '.join(':' + col for col in CSV_FIELDS) + ')', dict(data, user_id=g.user['id']))
                existing.add(key)
                inserted += 1
        flash(f'Imported {inserted} applications; skipped {skipped} duplicates.', 'success')
        return redirect(url_for('index'))

    def parse_form():
        data = {key: request.form.get(key, '').strip() for key in ('company', 'position', 'location', 'status', 'applied_date', 'job_url', 'notes', 'follow_up_date', 'interview_date')}
        if not data['company'] or not data['position']:
            return None, 'Company and position are required.'
        if data['status'] not in STATUSES:
            return None, 'Choose a valid status.'
        try:
            date.fromisoformat(data['applied_date'])
        except ValueError:
            return None, 'Enter a valid application date.'
        for field, label in (('follow_up_date', 'follow-up'), ('interview_date', 'interview')):
            if data[field]:
                try:
                    date.fromisoformat(data[field])
                except ValueError:
                    return None, f'Enter a valid {label} date.'
        if data['job_url'] and not data['job_url'].startswith(('https://', 'http://')):
            return None, 'Job URL must start with http:// or https://.'
        return data, None

    @app.route('/new', methods=['GET', 'POST'])
    @login_required
    def new():
        if request.method == 'POST':
            data, error = parse_form()
            if error:
                flash(error, 'error')
                return render_template('form.html', application=request.form, statuses=STATUSES, today=date.today().isoformat(), heading='Add application'), 400
            with connect() as db:
                db.execute('INSERT INTO applications (user_id, company, position, location, status, applied_date, job_url, notes, follow_up_date, interview_date) VALUES (:user_id, :company, :position, :location, :status, :applied_date, :job_url, :notes, :follow_up_date, :interview_date)', dict(data, user_id=g.user['id']))
            flash('Application added.', 'success')
            return redirect(url_for('index'))
        return render_template('form.html', application={}, statuses=STATUSES, today=date.today().isoformat(), heading='Add application')

    @app.route('/edit/<int:application_id>', methods=['GET', 'POST'])
    @login_required
    def edit(application_id):
        with connect() as db:
            application = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (application_id, g.user['id'])).fetchone()
        if application is None:
            abort(404)
        if request.method == 'POST':
            data, error = parse_form()
            if error:
                flash(error, 'error')
                return render_template('form.html', application=request.form, statuses=STATUSES, today=date.today().isoformat(), heading='Edit application'), 400
            data['id'] = application_id
            with connect() as db:
                db.execute('UPDATE applications SET company=:company, position=:position, location=:location, status=:status, applied_date=:applied_date, job_url=:job_url, notes=:notes, follow_up_date=:follow_up_date, interview_date=:interview_date WHERE id=:id AND user_id=:user_id', dict(data, user_id=g.user['id']))
            flash('Application updated.', 'success')
            return redirect(url_for('index'))
        return render_template('form.html', application=dict(application), statuses=STATUSES, today=date.today().isoformat(), heading='Edit application')

    @app.post('/delete/<int:application_id>')
    @login_required
    def delete(application_id):
        with connect() as db:
            result = db.execute('DELETE FROM applications WHERE id = ? AND user_id = ?', (application_id, g.user['id']))
            if not result.rowcount:
                abort(404)
        flash('Application deleted.', 'success')
        return redirect(url_for('index'))

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
