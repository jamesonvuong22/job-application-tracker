import sqlite3
from datetime import date, timedelta
from app import create_app

def post(client, path, **kwargs):
    with client.session_transaction() as sess:
        token = sess['csrf_token']
    kwargs.setdefault('data', {})
    kwargs['data']['csrf_token'] = token
    return client.post(path, **kwargs)

def signup(client, email='tester@example.com'):
    client.get('/register')
    result = post(client, '/register', data={'email': email, 'password': 'very-secure-password-123'})
    assert result.status_code == 302

import pytest

@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'test.db')})
    client = app.test_client()
    signup(client)
    return client, app

def sample(**kwargs):
    data = {'company': 'Acme', 'position': 'Intern', 'status': 'Applied', 'location': '', 'applied_date': date.today().isoformat(), 'job_url': '', 'notes': '', 'follow_up_date': '', 'interview_date': ''}
    data.update(kwargs)
    return data

def test_deadline_display_and_filters(client):
    http, _ = client
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert post(http, '/new', data=sample(company='Late', follow_up_date=yesterday)).status_code == 302
    post(http, '/new', data=sample(company='Today', follow_up_date=date.today().isoformat()))
    post(http, '/new', data=sample(company='Future', follow_up_date=tomorrow, interview_date=tomorrow))
    post(http, '/new', data=sample(company='Closed', status='Rejected', follow_up_date=yesterday))
    page = http.get('/').data
    assert b'Follow-up reminders' in page and b'Overdue' in page
    assert b'Late' in http.get('/?deadline=overdue').data
    assert b'Closed' not in http.get('/?deadline=overdue').data
    assert b'Future' in http.get('/?deadline=upcoming').data
    assert b'Today' in http.get('/?deadline=today').data
    assert tomorrow.encode() in page

def test_edit_dates_and_validation(client):
    http, _ = client
    post(http, '/new', data=sample())
    assert post(http, '/edit/1', data=sample(follow_up_date='2026-12-12', interview_date='2026-12-11')).status_code == 302
    assert b'2026-12-11' in http.get('/').data
    assert post(http, '/edit/1', data=sample(follow_up_date='tomorrow')).status_code == 400
    assert post(http, '/new', data=sample(interview_date='2026-99-99')).status_code == 400

def test_existing_v1_database_migrates(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE applications (id INTEGER PRIMARY KEY, company TEXT, position TEXT, location TEXT, status TEXT, applied_date TEXT, job_url TEXT, notes TEXT, created_at TEXT)")
        db.execute("INSERT INTO applications VALUES (1,'LegacyCo','Engineer','','Applied','2026-10-01','','','')")
    app = create_app({'TESTING': True, 'DATABASE': str(path)})
    client = app.test_client()
    signup(client)
    assert b'LegacyCo' in client.get('/').data
    # Repeated startup must not repeat migrations or lose data.
    create_app({'TESTING': True, 'DATABASE': str(path)})
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT follow_up_date, interview_date FROM applications WHERE id=1').fetchone() == ('', '')
