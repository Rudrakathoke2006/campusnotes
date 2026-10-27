import os
import sys
import tempfile
import shutil
import io
import pytest

# Ensure the CampusNotes stage3 application is imported
STAGE3_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'campusnotes-project', 'stages', 'stage3'))
if STAGE3_DIR not in sys.path:
    sys.path.insert(0, STAGE3_DIR)

import app as campusnotes_app


@pytest.fixture
def client():
    """Sets up an isolated test client with a clean temporary SQLite database and upload directory."""
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_notes.db')
    test_uploads = os.path.join(temp_dir, 'test_uploads')
    os.makedirs(test_uploads, exist_ok=True)

    # Re-point application paths to temporary environment
    campusnotes_app.DB_FILE = test_db
    campusnotes_app.UPLOAD_DIR = test_uploads
    campusnotes_app.app.config['TESTING'] = True
    campusnotes_app.app.config['SECRET_KEY'] = 'test-secret-key-campusnotes'

    # Initialize tables
    campusnotes_app.init_db()

    with campusnotes_app.app.test_client() as test_client:
        yield test_client

    # Teardown temporary directory
    shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# WHITE-BOX TESTS: HELPER & UTILITY FUNCTIONS
# ============================================================================

def test_is_pdf_validation():
    """White-box test: is_pdf() correctly checks file extension branches."""
    class DummyFile:
        def __init__(self, filename):
            self.filename = filename

    # True branches
    assert campusnotes_app.is_pdf(DummyFile('lecture_notes.pdf')) is True
    assert campusnotes_app.is_pdf(DummyFile('ASSIGNMENT.PDF')) is True

    # False branches
    assert campusnotes_app.is_pdf(DummyFile('notes.txt')) is False
    assert campusnotes_app.is_pdf(DummyFile('image.png')) is False
    assert campusnotes_app.is_pdf(None) is None or campusnotes_app.is_pdf(None) == False


# ============================================================================
# WHITE-BOX TESTS: AUTHENTICATION & ACCESS CONTROL (OPEN TO ALL STUDENTS)
# ============================================================================

def test_signup_get_page(client):
    """White-box test: GET /signup renders account registration form."""
    res = client.get('/signup')
    assert res.status_code == 200
    assert b'Create an Account' in res.data or b'Sign Up' in res.data or b'signup' in res.data.lower()


def test_signup_success(client):
    """White-box test: POST /signup creates a new user with hashed password and redirects to /login."""
    res = client.post('/signup', data={
        'email': 'student1@campus.edu',
        'password': 'SecurePassword123'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Account created. Log in to continue.' in res.data


def test_signup_duplicate_email_error(client):
    """White-box test: POST /signup catches sqlite3.IntegrityError when email already exists."""
    # First registration
    client.post('/signup', data={
        'email': 'duplicate@campus.edu',
        'password': 'Password123'
    })

    # Second registration with same email
    res = client.post('/signup', data={
        'email': 'duplicate@campus.edu',
        'password': 'AnotherPassword456'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'That email is already registered.' in res.data


def test_login_get_page(client):
    """White-box test: GET /login renders login form."""
    res = client.get('/login')
    assert res.status_code == 200
    assert b'Sign in to access and share campus notes' in res.data


def test_login_success(client):
    """White-box test: POST /login authenticates valid user and establishes session."""
    client.post('/signup', data={
        'email': 'validuser@campus.edu',
        'password': 'MyPassword123'
    })

    res = client.post('/login', data={
        'email': 'validuser@campus.edu',
        'password': 'MyPassword123'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Shared Notes Repository' in res.data
    assert b'validuser@campus.edu' in res.data


def test_login_invalid_password(client):
    """White-box test: POST /login rejects incorrect password for registered user."""
    client.post('/signup', data={
        'email': 'validuser@campus.edu',
        'password': 'CorrectPassword'
    })

    res = client.post('/login', data={
        'email': 'validuser@campus.edu',
        'password': 'WrongPassword999'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Wrong email or password.' in res.data


def test_login_unregistered_email(client):
    """White-box test: POST /login rejects non-existent email."""
    res = client.post('/login', data={
        'email': 'nonexistent@campus.edu',
        'password': 'Password123'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Wrong email or password.' in res.data


def test_login_required_protected_routes(client):
    """White-box test: @login_required decorator intercepts unauthenticated requests and redirects to /login."""
    for path in ['/', '/download/1']:
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 302
        assert '/login' in res.headers['Location']


def test_logout(client):
    """White-box test: GET /logout clears session and redirects to /login."""
    # Register and log in
    client.post('/signup', data={'email': 'user@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'user@campus.edu', 'password': 'Pass123'})

    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b'Sign in to access and share campus notes' in res.data


# ============================================================================
# WHITE-BOX TESTS: NOTES DASHBOARD, UPLOAD, DOWNLOAD & REPLACE
# ============================================================================

def test_dashboard_empty_repository(client):
    """White-box test: GET / displays repository when no notes are uploaded."""
    client.post('/signup', data={'email': 'user@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'user@campus.edu', 'password': 'Pass123'})

    res = client.get('/')
    assert res.status_code == 200
    assert b'Shared Notes Repository' in res.data
    assert b'0 available' in res.data


def test_upload_note_pdf_success(client):
    """White-box test: POST /upload with valid PDF stores file on disk and inserts record."""
    client.post('/signup', data={'email': 'author@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'author@campus.edu', 'password': 'Pass123'})

    pdf_data = {
        'title': 'Cloud Computing Lecture 1',
        'subject': 'CS401',
        'file': (io.BytesIO(b'%PDF-1.4 sample lecture content'), 'lecture1.pdf')
    }
    res = client.post('/upload', data=pdf_data, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'Note uploaded.' in res.data
    assert b'Cloud Computing Lecture 1' in res.data
    assert b'CS401' in res.data
    assert b'author@campus.edu' in res.data


def test_upload_note_invalid_file_rejected(client):
    """White-box test: POST /upload blocks non-PDF documents and displays alert."""
    client.post('/signup', data={'email': 'author@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'author@campus.edu', 'password': 'Pass123'})

    invalid_data = {
        'title': 'Malicious or Text Document',
        'subject': 'CS401',
        'file': (io.BytesIO(b'plain text notes'), 'notes.txt')
    }
    res = client.post('/upload', data=invalid_data, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'Only PDF files are allowed.' in res.data


def test_download_note_success(client):
    """White-box test: GET /download/<id> serves the stored PDF file."""
    client.post('/signup', data={'email': 'author@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'author@campus.edu', 'password': 'Pass123'})

    pdf_content = b'%PDF-1.4 downloaded notes stream'
    client.post('/upload', data={
        'title': 'Database Notes',
        'subject': 'DBMS',
        'file': (io.BytesIO(pdf_content), 'dbms.pdf')
    }, content_type='multipart/form-data')

    res = client.get('/download/1')
    assert res.status_code == 200
    assert res.data == pdf_content


def test_download_nonexistent_note_returns_404(client):
    """White-box test: GET /download/<id> returns 404 when note ID is not found."""
    client.post('/signup', data={'email': 'user@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'user@campus.edu', 'password': 'Pass123'})

    res = client.get('/download/999')
    assert res.status_code == 404
    assert b'Note not found' in res.data


def test_replace_note_by_owner_success(client):
    """White-box test: Note owner can replace their note with an updated PDF."""
    client.post('/signup', data={'email': 'owner@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'owner@campus.edu', 'password': 'Pass123'})

    # Upload original note
    client.post('/upload', data={
        'title': 'Operating Systems',
        'subject': 'OS',
        'file': (io.BytesIO(b'%PDF-1.4 version 1'), 'os_v1.pdf')
    }, content_type='multipart/form-data')

    # Replace with updated PDF
    new_pdf = b'%PDF-1.4 version 2 updated'
    res = client.post('/replace/1', data={
        'file': (io.BytesIO(new_pdf), 'os_v2.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'File replaced.' in res.data

    # Verify downloaded file is now version 2
    dl_res = client.get('/download/1')
    assert dl_res.data == new_pdf


def test_replace_note_by_different_user_forbidden(client):
    """White-box test: User cannot replace a note owned by another student."""
    # User 1 uploads note 1
    client.post('/signup', data={'email': 'user1@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'user1@campus.edu', 'password': 'Pass123'})
    client.post('/upload', data={
        'title': 'Original Note',
        'subject': 'CS101',
        'file': (io.BytesIO(b'%PDF-1.4 original'), 'orig.pdf')
    }, content_type='multipart/form-data')
    client.get('/logout')

    # User 2 logs in and attempts to replace note 1
    client.post('/signup', data={'email': 'user2@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'user2@campus.edu', 'password': 'Pass123'})

    res = client.post('/replace/1', data={
        'file': (io.BytesIO(b'%PDF-1.4 attacker overwrite'), 'exploit.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'You can only replace your own notes with a PDF.' in res.data


def test_replace_note_invalid_file_rejected(client):
    """White-box test: Replacing note with non-PDF file is rejected."""
    client.post('/signup', data={'email': 'owner@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'owner@campus.edu', 'password': 'Pass123'})

    client.post('/upload', data={
        'title': 'Networks',
        'subject': 'CN',
        'file': (io.BytesIO(b'%PDF-1.4 cn_v1'), 'cn.pdf')
    }, content_type='multipart/form-data')

    res = client.post('/replace/1', data={
        'file': (io.BytesIO(b'plain text invalid'), 'cn.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'You can only replace your own notes with a PDF.' in res.data


def test_replace_nonexistent_note_rejected(client):
    """White-box test: Attempting to replace a non-existent note ID fails safely."""
    client.post('/signup', data={'email': 'owner@campus.edu', 'password': 'Pass123'})
    client.post('/login', data={'email': 'owner@campus.edu', 'password': 'Pass123'})

    res = client.post('/replace/999', data={
        'file': (io.BytesIO(b'%PDF-1.4 new'), 'new.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    assert b'You can only replace your own notes with a PDF.' in res.data
