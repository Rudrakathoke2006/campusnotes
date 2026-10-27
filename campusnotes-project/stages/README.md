# Build-from-scratch stages (run on your laptop, no AWS needed)

stage1  Frontend + minimal backend. Notes are kept in memory.
stage2  Adds a real database (SQLite) so notes survive restarts.
stage3  Adds sign-up/login (hashed passwords, sessions) and PDF upload/download to a local folder.
../app  The cloud version: Cognito for users, Aurora (MySQL) for data, S3 for files.

Run any stage:
    cd stages/stage3
    python -m venv venv            (Windows: py -m venv venv)
    venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
    pip install flask
    python app.py                  (Windows: py app.py)
Open http://127.0.0.1:8000
