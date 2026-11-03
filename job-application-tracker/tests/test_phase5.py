
import io
import sqlite3
from app import create_app


def start(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-key',
        'DATABASE': str(tmp_path / 'auth.db')
    })
    return app, app.test_client()


def post(client, path, data=None, **kwargs):
    with client.session_transaction() as sess:
        token = sess.get('csrf_token')

    data = dict(data or {}, csrf_token=token)
    return client.post(path, data=data, **kwargs)


def register(client, email):
    client.get('/register')
    return post(client, '/register', {
        'email': email,
        'password': 'strong_password_1234'
    })


def test_authentication_and_password_hashing(tmp_path):
    app, c = start(tmp_path)

    assert c.get('/').status_code == 302
    assert c.get('/export/csv').status_code == 302

    assert register(c, 'alice@example.com').status_code == 302
    assert b'Application dashboard' in c.get('/').data

    # Verify that passwords are stored as hashes
    with sqlite3.connect(app.config['DATABASE']) as db:
        stored = db.execute(
            'SELECT password_hash FROM users'
        ).fetchone()[0]

    assert stored != 'strong_password_1234'

    # Log out
    assert post(c, '/logout').status_code == 302

    # FIX: Reload login page to generate a new CSRF token
    assert c.get('/login').status_code == 200

    # Incorrect password should return 401
    assert post(c, '/login', {
        'email': 'alice@example.com',
        'password': 'wrong'
    }).status_code == 401

    # Correct password should allow login
    assert post(c, '/login', {
        'email': 'alice@example.com',
        'password': 'strong_password_1234'
    }).status_code == 302

    # Already logged-in users should be redirected
    assert register(c, 'alice@example.com').status_code == 302


def test_duplicate_and_short_password(tmp_path):
    _, c = start(tmp_path)

    c.get('/register')

    # Short passwords should be rejected
    assert post(c, '/register', {
        'email': 'alice@example.com',
        'password': 'short'
    }).status_code == 400

    # Register with a valid password
    assert register(c, 'alice@example.com').status_code == 302

    # Log out
    assert post(c, '/logout').status_code == 302

    # FIX: Generate a new CSRF token after logging out
    assert c.get('/register').status_code == 200

    # Duplicate emails should be rejected
    assert post(c, '/register', {
        'email': 'ALICE@example.com',
        'password': 'strong_password_1234'
    }).status_code == 400


def test_csrf_blocks_submission(tmp_path):
    _, c = start(tmp_path)

    c.get('/register')

    # Registration without CSRF token should fail
    assert c.post('/register', data={
        'email': 'a@b.example',
        'password': 'strong_password_1234'
    }).status_code == 400

    # Register successfully
    register(c, 'a@b.example')

    # Creating an application without CSRF should fail
    assert c.post('/new', data={
        'company': 'Unsafe'
    }).status_code == 400

    # Logging out without CSRF should fail
    assert c.post('/logout').status_code == 400


def test_user_data_isolation_and_csv(tmp_path):
    app, alice = start(tmp_path)

    register(alice, 'alice@example.com')

    record = {
        'company': 'AliceOnly',
        'position': 'Intern',
        'status': 'Applied',
        'applied_date': '2026-10-20'
    }

    # Alice creates an application
    assert post(alice, '/new', record).status_code == 302

    # Bob creates a separate account
    bob = app.test_client()
    register(bob, 'bob@example.com')

    # Bob cannot see Alice's applications
    assert b'AliceOnly' not in bob.get('/').data
    assert b'AliceOnly' not in bob.get('/analytics').data
    assert b'AliceOnly' not in bob.get('/export/csv').data

    # Bob cannot modify Alice's applications
    assert bob.get('/edit/1').status_code == 404
    assert post(bob, '/edit/1', record).status_code == 404
    assert post(bob, '/delete/1').status_code == 404

    # Alice can still see her own application
    assert b'AliceOnly' in alice.get('/').data

    # Bob imports his own CSV data
    csv_data = (
        b'company,position,applied_date\n'
        b'AliceOnly,Intern,2026-10-20\n'
    )

    assert post(
        bob,
        '/import/csv',
        {
            'file': (
                io.BytesIO(csv_data),
                'sample.csv'
            )
        },
        content_type='multipart/form-data'
    ).status_code == 302

    # Both users now have independent application records
    assert b'AliceOnly' in bob.get('/').data
    assert b'AliceOnly' in alice.get('/').data


def test_legacy_claim_only_once(tmp_path):
    path = tmp_path / 'legacy.db'

    # Simulate a database from an older version
    with sqlite3.connect(path) as db:
        db.execute(
            'CREATE TABLE applications ('
            'id INTEGER PRIMARY KEY, '
            'company TEXT, '
            'position TEXT, '
            'location TEXT, '
            'status TEXT, '
            'applied_date TEXT, '
            'job_url TEXT, '
            'notes TEXT, '
            'created_at TEXT)'
        )

        db.execute(
            "INSERT INTO applications VALUES "
            "(1, 'LegacyCo', 'Engineer', '', "
            "'Applied', '2026-10-01', '', '', '')"
        )

    # Upgrade the old database
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-key',
        'DATABASE': str(path)
    })

    # First registered user inherits old records
    c1 = app.test_client()
    register(c1, 'first@example.com')

    assert b'LegacyCo' in c1.get('/').data

    # Second user must not inherit old records
    c2 = app.test_client()
    register(c2, 'second@example.com')

    assert b'LegacyCo' not in c2.get('/').data

    # Restarting the application preserves ownership
    create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-key',
        'DATABASE': str(path)
    })

    assert b'LegacyCo' in c1.get('/').data
