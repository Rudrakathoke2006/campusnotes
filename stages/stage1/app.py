from flask import Flask, render_template, request, redirect, flash

app = Flask(__name__)
app.secret_key = 'dev-only-key'

# Notes live in a Python list, so they vanish when the program stops
NOTES = [{'id': 1, 'title': 'Sample note', 'subject': 'Maths',
          'owner': 'you@example.com'}]


@app.route('/')
def index():
    return render_template('index.html', notes=NOTES)


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/upload', methods=['POST'])
def upload():
    NOTES.append({'id': len(NOTES) + 1, 'title': request.form['title'],
                  'subject': request.form['subject'],
                  'owner': 'you@example.com'})
    flash('Note added (kept in memory only).')
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, port=8000)
