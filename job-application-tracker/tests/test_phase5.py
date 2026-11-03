import io
import sqlite3
from app import create_app


def start(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-key', 'DATABASE': str(tmp_path / 'auth.db')})
    return app, app.test_client()


def post(client, path, data=None, **kwargs):
    with client.session_transaction() as sess:
        token = sess.get('csrf_token')
    data = dict(data or {}, csrf_token=token)
    return client.post(path, data=data, **kwargs)


def register(client, email):
    client.get('/register')
    return post(client, '/register', {'email': email, 'password': 'strong_password_1234'})


def test_authentication_and_password_hashing(tmp_path):
    app, c = start(tmp_path)
    assert c.get('/').status_code == 302
    assert c.get('/export/csv').status_code == 302
    assert register(c, 'alice@example.com').status_code == 302
    assert b'Application dashboard' in c.get('/').data
    with sqlite3.connect(app.config['DATABASE']) as db:
        stored = db.execute('SELECT password_hash FROM users').fetchone()[0]
    assert stored != 'strong_password_1234'
    assert post(c, '/logout').status_code == 302
    assert post(c, '/login', {'email': 'alice@example.com', 'password': 'wrong'}).status_code == 401
    assert post(c, '/login', {'email': 'alice@example.com', 'password': 'strong_password_1234'}).status_code == 302
    assert register(c, 'alice@example.com').status_code == 302  # Already logged in, redirects.


def test_duplicate_and_short_password(tmp_path):
    _, c = start(tmp_path)
    c.get('/register')
    assert post(c, '/register', {'email': 'alice@example.com', 'password': 'short'}).status_code == 400
    register(c, 'alice@example.com')
    post(c, '/logout')
    assert post(c, '/register', {'email': 'ALICE@example.com', 'password': 'strong_password_1234'}).status_code == 400


def test_csrf_blocks_submission(tmp_path):
    _, c = start(tmp_path)
    c.get('/register')
    assert c.post('/register', data={'email': 'a@b.example', 'password': 'strong_password_1234'}).status_code == 400
    register(c, 'a@b.example')
    assert c.post('/new', data={'company': 'Unsafe'}).status_code == 400
    assert c.post('/logout').status_code == 400


def test_user_data_isolation_and_csv(tmp_path):
    app, alice = start(tmp_path)
    register(alice, 'alice@example.com')
    record = {'company': 'AliceOnly', 'position': 'Intern', 'status': 'Applied', 'applied_date': '2026-10-20'}
    assert post(alice, '/new', record).status_code == 302
    bob = app.test_client()
    register(bob, 'bob@example.com')
    assert b'AliceOnly' not in bob.get('/').data
    assert b'AliceOnly' not in bob.get('/analytics').data
    assert b'AliceOnly' not in bob.get('/export/csv').data
    assert bob.get('/edit/1').status_code == 404
    assert post(bob, '/edit/1', record).status_code == 404
    assert post(bob, '/delete/1').status_code == 404
    assert b'AliceOnly' in alice.get('/').data
    csv_data = b'company,position,applied_date\nAliceOnly,Intern,2026-10-20\n'
    assert post(bob, '/import/csv', {'file': (io.BytesIO(csv_data), 'sample.csv')}, content_type='multipart/form-data').status_code == 302
    assert b'AliceOnly' in bob.get('/').data
    assert b'AliceOnly' in alice.get('/').data


def test_legacy_claim_only_once(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE applications (id INTEGER PRIMARY KEY, company TEXT, position TEXT, location TEXT, status TEXT, applied_date TEXT, job_url TEXT, notes TEXT, created_at TEXT)')
        db.execute("INSERT INTO applications VALUES (1, 'LegacyCo', 'Engineer', '', 'Applied', '2026-10-01', '', '', '')")
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-key', 'DATABASE': str(path)})
    c1 = app.test_client()
    register(c1, 'first@example.com')
    assert b'LegacyCo' in c1.get('/').data
    c2 = app.test_client()
    register(c2, 'second@example.com')
    assert b'LegacyCo' not in c2.get('/').data
    create_app({'TESTING': True, 'SECRET_KEY': 'test-key', 'DATABASE': str(path)})
    assert b'LegacyCo' in c1.get('/').data
