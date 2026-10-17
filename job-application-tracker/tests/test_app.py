import pytest
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'test.db')})
    return app.test_client()


def sample(**changes):
    data = {'company': 'Example Inc', 'position': 'Software Intern', 'location': 'Toronto', 'status': 'Applied', 'applied_date': '2026-10-17', 'job_url': 'https://example.com/job', 'notes': 'Follow up'}
    data.update(changes)
    return data


def test_dashboard(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Application dashboard' in response.data


def test_create_edit_search_delete(client):
    assert client.post('/new', data=sample(), follow_redirects=True).status_code == 200
    assert b'Example Inc' in client.get('/?q=Example').data
    assert b'Example Inc' not in client.get('/?q=Missing').data
    assert client.post('/edit/1', data=sample(status='Interview'), follow_redirects=True).status_code == 200
    assert b'Interview' in client.get('/?status=Interview').data
    assert client.post('/delete/1', follow_redirects=True).status_code == 200
    assert b'Example Inc' not in client.get('/').data


def test_invalid_submission(client):
    assert client.post('/new', data=sample(company='')).status_code == 400
    assert client.post('/new', data=sample(status='Invalid')).status_code == 400
    assert client.post('/new', data=sample(applied_date='not-a-date')).status_code == 400
    assert client.post('/new', data=sample(job_url='javascript:alert(1)')).status_code == 400


def test_missing_application(client):
    assert client.get('/edit/999').status_code == 404
    assert client.post('/delete/999').status_code == 404
