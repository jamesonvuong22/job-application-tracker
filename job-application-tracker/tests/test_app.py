import pytest
from app import create_app
from werkzeug.test import EnvironBuilder

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


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'test.db')})
    client = app.test_client()
    signup(client)
    return client


def sample(**changes):
    data = {'company': 'Example Inc', 'position': 'Software Intern', 'location': 'Toronto', 'status': 'Applied', 'applied_date': '2026-10-17', 'job_url': 'https://example.com/job', 'notes': 'Follow up'}
    data.update(changes)
    return data


def test_dashboard(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Application dashboard' in response.data


def test_create_edit_search_delete(client):
    assert post(client, '/new', data=sample(), follow_redirects=True).status_code == 200
    assert b'Example Inc' in client.get('/?q=Example').data
    assert b'Example Inc' not in client.get('/?q=Missing').data
    assert post(client, '/edit/1', data=sample(status='Interview'), follow_redirects=True).status_code == 200
    assert b'Interview' in client.get('/?status=Interview').data
    assert post(client, '/delete/1', follow_redirects=True).status_code == 200
    assert b'Example Inc' not in client.get('/').data


def test_invalid_submission(client):
    assert post(client, '/new', data=sample(company='')).status_code == 400
    assert post(client, '/new', data=sample(status='Invalid')).status_code == 400
    assert post(client, '/new', data=sample(applied_date='not-a-date')).status_code == 400
    assert post(client, '/new', data=sample(job_url='javascript:alert(1)')).status_code == 400


def test_missing_application(client):
    assert client.get('/edit/999').status_code == 404
    assert post(client, '/delete/999').status_code == 404
