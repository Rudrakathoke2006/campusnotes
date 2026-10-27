import os, sqlite3, uuid, functools
from flask import (Flask, render_template, request, redirect, flash, g,
                   session, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'dev-only-key'          # signs the login cookie
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'notes.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.context_processor
def inject_metadata():
    return dict(instance='Localhost (Dev)', az='Local Environment', announcement='')



def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY, password_hash TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, subject TEXT, owner TEXT, file_key TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()


init_db()


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        if 'user' not in session:
            return redirect('/login')
        return f(*a, **k)
    return wrapper


def is_pdf(f):
    return f and f.filename.lower().endswith('.pdf')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        try:
            db().execute('INSERT INTO users VALUES(?,?)', (
                email, generate_password_hash(request.form['password'])))
            db().commit()
            flash('Account created. Log in to continue.')
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash('That email is already registered.')
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        row = db().execute('SELECT password_hash FROM users WHERE email=?',
                           (email,)).fetchone()
        if row and check_password_hash(row['password_hash'],
                                       request.form['password']):
            session['user'] = email
            return redirect('/')
        flash('Wrong email or password.')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/')
@login_required
def index():
    rows = db().execute(
        'SELECT id, title, subject, owner FROM notes ORDER BY id DESC'
    ).fetchall()
    return render_template('index.html', notes=rows)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    f = request.files.get('file')
    if not is_pdf(f):
        flash('Only PDF files are allowed.')
        return redirect('/')
    key = '%s-%s' % (uuid.uuid4(), secure_filename(f.filename))
    f.save(os.path.join(UPLOAD_DIR, key))
    db().execute(
        'INSERT INTO notes(title, subject, owner, file_key) VALUES(?,?,?,?)',
        (request.form['title'], request.form['subject'], session['user'], key))
    db().commit()
    flash('Note uploaded.')
    return redirect('/')


@app.route('/replace/<int:nid>', methods=['POST'])
@login_required
def replace(nid):
    f = request.files.get('file')
    row = db().execute('SELECT file_key, owner FROM notes WHERE id=?',
                       (nid,)).fetchone()
    if not row or row['owner'] != session['user'] or not is_pdf(f):
        flash('You can only replace your own notes with a PDF.')
        return redirect('/')
    f.save(os.path.join(UPLOAD_DIR, row['file_key']))   # overwrites the file
    flash('File replaced.')
    return redirect('/')


@app.route('/download/<int:nid>')
@login_required
def download(nid):
    row = db().execute('SELECT file_key FROM notes WHERE id=?',
                       (nid,)).fetchone()
    if not row:
        return 'Note not found', 404
    return send_from_directory(UPLOAD_DIR, row['file_key'])


if __name__ == '__main__':
    app.run(debug=True, port=8000)
