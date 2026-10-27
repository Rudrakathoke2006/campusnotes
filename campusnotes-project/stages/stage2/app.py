import os, sqlite3
from flask import Flask, render_template, request, redirect, flash, g

app = Flask(__name__)
app.secret_key = 'dev-only-key'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'notes.db')


def db():
    """One database connection per request."""
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
    conn.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, subject TEXT, owner TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()


init_db()


@app.route('/')
def index():
    rows = db().execute(
        'SELECT id, title, subject, owner FROM notes ORDER BY id DESC'
    ).fetchall()
    return render_template('index.html', notes=rows)


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/upload', methods=['POST'])
def upload():
    db().execute('INSERT INTO notes(title, subject, owner) VALUES(?,?,?)',
                 (request.form['title'], request.form['subject'],
                  'you@example.com'))
    db().commit()
    flash('Note saved in the database.')
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, port=8000)
