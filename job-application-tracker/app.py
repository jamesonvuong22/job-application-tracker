import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, abort, flash, redirect, render_template, request, url_for

STATUSES = ('Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected', 'Withdrawn')


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', 'local-development-only'), DATABASE=os.environ.get('DATABASE', str(Path(app.instance_path) / 'applications.db')))
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

    @app.get('/')
    def index():
        search = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        deadline_filter = request.args.get('deadline', '').strip()
        today = date.today().isoformat()
        sql = 'SELECT * FROM applications WHERE 1=1'
        args = []
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
            counts = {row['status']: row['total'] for row in db.execute('SELECT status, COUNT(*) AS total FROM applications GROUP BY status')}
            deadline_counts = dict(db.execute("""SELECT
                SUM(CASE WHEN follow_up_date != '' AND follow_up_date < ? THEN 1 ELSE 0 END) AS overdue,
                SUM(CASE WHEN follow_up_date = ? THEN 1 ELSE 0 END) AS today,
                SUM(CASE WHEN follow_up_date > ? THEN 1 ELSE 0 END) AS upcoming
                FROM applications WHERE status NOT IN ('Offer','Rejected','Withdrawn')""", (today, today, today)).fetchone())
        return render_template('index.html', applications=applications, counts=counts, statuses=STATUSES, search=search, selected_status=status, deadline_filter=deadline_filter, deadline_counts=deadline_counts, today=today)


    @app.get('/analytics')
    def analytics():
        """Aggregate actual application records without storing duplicate analytics data."""
        period = request.args.get('period', 'all')
        if period not in ('all', '30', '90'):
            period = 'all'
        where = ''
        params = ()
        if period != 'all':
            # Inclusive calendar window: today plus the previous N-1 days.
            start = (date.today() - timedelta(days=int(period) - 1)).isoformat()
            where = ' WHERE applied_date >= ? AND applied_date <= ?'
            params = (start, date.today().isoformat())
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
    def new():
        if request.method == 'POST':
            data, error = parse_form()
            if error:
                flash(error, 'error')
                return render_template('form.html', application=request.form, statuses=STATUSES, today=date.today().isoformat(), heading='Add application'), 400
            with connect() as db:
                db.execute('INSERT INTO applications (company, position, location, status, applied_date, job_url, notes, follow_up_date, interview_date) VALUES (:company, :position, :location, :status, :applied_date, :job_url, :notes, :follow_up_date, :interview_date)', data)
            flash('Application added.', 'success')
            return redirect(url_for('index'))
        return render_template('form.html', application={}, statuses=STATUSES, today=date.today().isoformat(), heading='Add application')

    @app.route('/edit/<int:application_id>', methods=['GET', 'POST'])
    def edit(application_id):
        with connect() as db:
            application = db.execute('SELECT * FROM applications WHERE id = ?', (application_id,)).fetchone()
        if application is None:
            abort(404)
        if request.method == 'POST':
            data, error = parse_form()
            if error:
                flash(error, 'error')
                return render_template('form.html', application=request.form, statuses=STATUSES, today=date.today().isoformat(), heading='Edit application'), 400
            data['id'] = application_id
            with connect() as db:
                db.execute('UPDATE applications SET company=:company, position=:position, location=:location, status=:status, applied_date=:applied_date, job_url=:job_url, notes=:notes, follow_up_date=:follow_up_date, interview_date=:interview_date WHERE id=:id', data)
            flash('Application updated.', 'success')
            return redirect(url_for('index'))
        return render_template('form.html', application=dict(application), statuses=STATUSES, today=date.today().isoformat(), heading='Edit application')

    @app.post('/delete/<int:application_id>')
    def delete(application_id):
        with connect() as db:
            result = db.execute('DELETE FROM applications WHERE id = ?', (application_id,))
            if not result.rowcount:
                abort(404)
        flash('Application deleted.', 'success')
        return redirect(url_for('index'))

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
