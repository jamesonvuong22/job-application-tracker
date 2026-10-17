import os
import sqlite3
from datetime import date
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

    @app.get('/')
    def index():
        search = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        sql = 'SELECT * FROM applications WHERE 1=1'
        args = []
        if search:
            sql += ' AND (company LIKE ? OR position LIKE ?)'
            args.extend([f'%{search}%', f'%{search}%'])
        if status in STATUSES:
            sql += ' AND status = ?'
            args.append(status)
        sql += ' ORDER BY applied_date DESC, id DESC'
        with connect() as db:
            applications = db.execute(sql, args).fetchall()
            counts = {row['status']: row['total'] for row in db.execute('SELECT status, COUNT(*) AS total FROM applications GROUP BY status')}
        return render_template('index.html', applications=applications, counts=counts, statuses=STATUSES, search=search, selected_status=status)

    def parse_form():
        data = {key: request.form.get(key, '').strip() for key in ('company', 'position', 'location', 'status', 'applied_date', 'job_url', 'notes')}
        if not data['company'] or not data['position']:
            return None, 'Company and position are required.'
        if data['status'] not in STATUSES:
            return None, 'Choose a valid status.'
        try:
            date.fromisoformat(data['applied_date'])
        except ValueError:
            return None, 'Enter a valid application date.'
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
                db.execute('INSERT INTO applications (company, position, location, status, applied_date, job_url, notes) VALUES (:company, :position, :location, :status, :applied_date, :job_url, :notes)', data)
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
                db.execute('UPDATE applications SET company=:company, position=:position, location=:location, status=:status, applied_date=:applied_date, job_url=:job_url, notes=:notes WHERE id=:id', data)
            flash('Application updated.', 'success')
            return redirect(url_for('index'))
        return render_template('form.html', application=application, statuses=STATUSES, today=date.today().isoformat(), heading='Edit application')

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
