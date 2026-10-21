import sqlite3
from datetime import date, timedelta
from app import create_app


def make_client(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'data.db')})
    return app.test_client(), app


def add(client, company, status='Applied', days_ago=0):
    return client.post('/new', data={
        'company': company, 'position': 'Intern', 'location': '',
        'status': status, 'applied_date': (date.today() - timedelta(days=days_ago)).isoformat(),
        'job_url': '', 'notes': '', 'follow_up_date': '', 'interview_date': ''
    })


def test_analytics_empty_and_navigation(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get('/analytics')
    assert page.status_code == 200
    assert b'Analytics dashboard' in page.data
    assert b'0.0%' in page.data
    assert b'Analytics' in client.get('/').data


def test_analytics_status_and_period(tmp_path):
    client, _ = make_client(tmp_path)
    add(client, 'RecentInterview', 'Interview')
    add(client, 'RecentOffer', 'Offer')
    add(client, 'OldRejected', 'Rejected', days_ago=120)
    all_page = client.get('/analytics').data
    assert b'3' in all_page and b'66.7%' in all_page
    recent = client.get('/analytics?period=30').data
    assert b'100.0%' in recent  # 2 of 2 in interview or offer
    assert b'Last 30 days' in recent


def test_invalid_period_and_edit_form(tmp_path):
    client, _ = make_client(tmp_path)
    add(client, 'Editable')
    assert client.get('/analytics?period=unexpected').status_code == 200
    edit = client.get('/edit/1')
    assert edit.status_code == 200
    assert b'Editable' in edit.data


def test_existing_database_not_reset(tmp_path):
    client, app = make_client(tmp_path)
    add(client, 'Preserved')
    create_app({'TESTING': True, 'DATABASE': app.config['DATABASE']})
    with sqlite3.connect(app.config['DATABASE']) as db:
        assert db.execute('SELECT COUNT(*) FROM applications').fetchone()[0] == 1
