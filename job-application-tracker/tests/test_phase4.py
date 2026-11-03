import csv
import io
import sqlite3
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
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'records.db')})
    client = app.test_client()
    signup(client)
    return client


def upload(client, text, name='applications.csv'):
    return post(client, '/import/csv', data={'file': (io.BytesIO(text.encode('utf-8')), name)},
                       content_type='multipart/form-data', follow_redirects=True)


def test_import_and_export(client):
    text = 'company,position,applied_date,status,notes\nAcme,Dev Intern,2026-10-17,Interview,Screening\n'
    resp = upload(client, text)
    assert b'Imported 1 applications' in resp.data
    resp = client.get('/export/csv')
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type
    parsed = list(csv.DictReader(io.StringIO(resp.data.decode('utf-8-sig'))))
    assert len(parsed) == 1
    assert parsed[0]['company'] == 'Acme'
    assert parsed[0]['status'] == 'Interview'
    assert parsed[0]['notes'] == 'Screening'


def test_duplicates_are_skipped(client):
    text = 'company,position,applied_date\nAcme,Developer,2026-10-17\nACME,developer,2026-10-17\n'
    response = upload(client, text)
    assert b'Imported 1 applications; skipped 1 duplicates' in response.data
    assert b'Imported 0 applications; skipped 2 duplicates' in upload(client, text).data


def test_invalid_file_atomic(client):
    text = 'company,position,applied_date\nAcme,Developer,2026-10-17\nBad,Developer,not-a-date\n'
    result = upload(client, text)
    assert b'Import cancelled' in result.data
    exported = client.get('/export/csv').data.decode('utf-8-sig')
    assert len(list(csv.DictReader(io.StringIO(exported)))) == 0


def test_upload_error_cases(client):
    assert b'Choose a .csv file' in upload(client, 'hi', 'records.txt').data
    assert b'unsupported columns' in upload(client, 'company,position,applied_date,unexpected\nA,B,2026-10-17,x\n').data
    assert b'incorrect number of fields' in upload(client, 'company,position,applied_date\nA,B,2026-10-17,EXTRA\n').data
    assert b'2 MB limit' in upload(client, 'x' * (2 * 1024 * 1024 + 1)).data


def test_empty_export_and_formula_protection(client):
    result = client.get('/export/csv')
    assert b'company,position' in result.data
    upload(client, 'company,position,applied_date,notes\nAcme,Developer,2026-10-17,=1+1\n')
    output = client.get('/export/csv').data.decode('utf-8-sig')
    assert "'=1+1" in output


def test_form_and_analytics_still_work(client):
    upload(client, 'company,position,applied_date\nAcme,Developer,2026-10-17\n')
    assert client.get('/analytics').status_code == 200
    assert client.get('/edit/1').status_code == 200
