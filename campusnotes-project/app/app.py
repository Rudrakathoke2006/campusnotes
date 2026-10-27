import os, json, uuid, logging, functools, urllib.request, shutil
import sqlite3
from datetime import datetime
from flask import (Flask, request, redirect, session, render_template,
                   flash, send_from_directory, g, jsonify, url_for)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Try importing AWS SDK dependencies. If not installed or AWS credentials/resources
# are not configured, the app seamlessly runs in Local Mode (SQLite + Local Storage).
try:
    import boto3, pymysql
    from botocore.config import Config
    from botocore.exceptions import ClientError
    AWS_SDK_AVAILABLE = True
except ImportError:
    AWS_SDK_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Settings from environment variables
REGION = os.environ.get('AWS_REGION', 'ap-south-1')
BUCKET = os.environ.get('BUCKET')
DB_HOST = os.environ.get('DB_HOST')
DB_SECRET = os.environ.get('DB_SECRET')
POOL_ID = os.environ.get('COGNITO_POOL_ID')
CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID')

# Check if we should run in Local Mode:
IS_LOCAL = (
    os.environ.get('LOCAL_DEV', '').lower() in ('1', 'true', 'yes')
    or not AWS_SDK_AVAILABLE
    or not all([BUCKET, DB_HOST, DB_SECRET, POOL_ID, CLIENT_ID])
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuscert-secure-key-2026-eval')
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB limit for high-res certificates

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

if IS_LOCAL:
    LOG_DIR = os.environ.get('LOG_DIR', os.path.join(BASE_DIR, 'logs'))
    SHARED_DIR = os.environ.get('SHARED_DIR', os.path.join(BASE_DIR, 'shared'))
    UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(BASE_DIR, 'uploads'))
    DB_FILE = os.environ.get('DB_FILE', os.path.join(BASE_DIR, 'certificates.db'))
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(SHARED_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    s3 = None
    cog = None
    _cred = None
else:
    LOG_DIR = os.environ.get('LOG_DIR', '/data/logs')       # EBS disk
    SHARED_DIR = os.environ.get('SHARED_DIR', '/mnt/efs')   # EFS shared disk
    UPLOAD_DIR = None
    DB_FILE = None
    s3 = boto3.client('s3', region_name=REGION,
                      config=Config(signature_version='s3v4'))
    cog = boto3.client('cognito-idp', region_name=REGION)
    _cred = None

try:
    log_file = os.path.join(LOG_DIR, 'app.log')
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format='%(asctime)s %(message)s')
except Exception:
    logging.basicConfig(level=logging.INFO)
log = logging.getLogger('campuscert')

if IS_LOCAL:
    log.info('Starting CampusCert in LOCAL MODE (SQLite + Local Storage)')
else:
    log.info('Starting CampusCert in AWS CLOUD MODE (Aurora + S3 + Cognito)')


def meta(path):
    """Read server metadata (instance id, zone) from AWS or report local dev."""
    if IS_LOCAL:
        if path == 'instance-id':
            return 'Localhost (Dev Server)'
        elif 'availability-zone' in path:
            return 'ap-south-1a (Local Emulation)'
        return 'Local'
    base = 'http://169.254.169.254/latest/'
    try:
        t = urllib.request.Request(
            base + 'api/token', method='PUT',
            headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'})
        tok = urllib.request.urlopen(t, timeout=1).read().decode()
        r = urllib.request.Request(
            base + 'meta-data/' + path,
            headers={'X-aws-ec2-metadata-token': tok})
        return urllib.request.urlopen(r, timeout=1).read().decode()
    except Exception:
        return 'AWS-EC2-Instance'


INSTANCE_ID = meta('instance-id')
AZ = meta('placement/availability-zone')


def announcement():
    """Banner text kept on the shared EFS disk (or local shared directory)."""
    try:
        announcement_file = os.path.join(SHARED_DIR, 'announcement.txt')
        if os.path.exists(announcement_file):
            with open(announcement_file, 'r', encoding='utf-8') as f:
                return f.read().strip()[:300]
    except Exception:
        pass
    return 'Faculty Notice: Academic Year 2025-26 certificate submissions are open. Please upload verified credentials for credit review.'


@app.context_processor
def inject():
    return dict(
        instance=INSTANCE_ID,
        az=AZ,
        announcement=announcement(),
        current_user=session.get('user'),
        current_role=session.get('role', 'student'),
        current_name=session.get('name', 'User')
    )


# --- Database Helpers ---
def get_local_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_local_db(error):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def db():
    """Open a connection to Aurora (AWS Mode) or SQLite (Local Mode)."""
    if IS_LOCAL:
        return get_local_db()

    global _cred
    if _cred is None:
        sm = boto3.client('secretsmanager', region_name=REGION)
        raw = sm.get_secret_value(SecretId=DB_SECRET)['SecretString']
        _cred = json.loads(raw)
    return pymysql.connect(
        host=DB_HOST, user=_cred['username'], password=_cred['password'],
        database='campusnotes', cursorclass=pymysql.cursors.DictCursor,
        autocommit=True, connect_timeout=5)


def init_db():
    if IS_LOCAL:
        is_new_db = not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) == 0
        conn = sqlite3.connect(DB_FILE)
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'student',
            roll_number TEXT,
            department TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        conn.execute('''CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            student_name TEXT NOT NULL,
            student_email TEXT NOT NULL,
            roll_number TEXT,
            category TEXT,
            issuing_org TEXT,
            issue_date TEXT,
            credential_url TEXT,
            s3_key TEXT NOT NULL,
            file_type TEXT DEFAULT 'pdf',
            status TEXT DEFAULT 'Pending',
            faculty_remarks TEXT,
            verified_by TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP)''')

        # Insert seed demo users & certificates if empty
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            demo_pass = generate_password_hash("Campus@123")
            # Student account
            conn.execute('''INSERT OR IGNORE INTO users 
                (email, password_hash, full_name, role, roll_number, department)
                VALUES (?, ?, ?, ?, ?, ?)''',
                ('student@campus.edu', demo_pass, 'Alex Chen', 'student', '21CS042', 'Computer Science & Engineering'))
            # Faculty account
            conn.execute('''INSERT OR IGNORE INTO users 
                (email, password_hash, full_name, role, roll_number, department)
                VALUES (?, ?, ?, ?, ?, ?)''',
                ('faculty@campus.edu', demo_pass, 'Dr. Sarah Mitchell', 'faculty', 'FAC-804', 'School of Engineering'))

            # Create dummy sample certificate files
            sample_pdf = os.path.join(UPLOAD_DIR, 'sample-aws-cert.pdf')
            if not os.path.exists(sample_pdf):
                with open(sample_pdf, 'wb') as sf:
                    sf.write(b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n')

            # Sample certificates: 1 Approved, 1 Pending, 1 Rejected
            conn.execute('''INSERT INTO certificates 
                (title, student_name, student_email, roll_number, category, issuing_org, issue_date, credential_url, s3_key, file_type, status, faculty_remarks, verified_by, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                ('AWS Certified Cloud Practitioner (CLF-C02)', 'Alex Chen', 'student@campus.edu', '21CS042',
                 'Industry Certification', 'Amazon Web Services', '2026-03-15', 'https://aws.amazon.com/verification',
                 'sample-aws-cert.pdf', 'pdf', 'Approved', 'Verified authentic from AWS validation portal. Awarded 10 activity points.',
                 'faculty@campus.edu', datetime.now().strftime('%Y-%m-%d %H:%M')))

            conn.execute('''INSERT INTO certificates 
                (title, student_name, student_email, roll_number, category, issuing_org, issue_date, credential_url, s3_key, file_type, status, faculty_remarks, verified_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                ('Deep Learning Specialization', 'Alex Chen', 'student@campus.edu', '21CS042',
                 'Online Course', 'DeepLearning.AI / Coursera', '2026-04-10', 'https://coursera.org/verify/SAMPLE123',
                 'sample-aws-cert.pdf', 'pdf', 'Pending', None, None))

            conn.execute('''INSERT INTO certificates 
                (title, student_name, student_email, roll_number, category, issuing_org, issue_date, credential_url, s3_key, file_type, status, faculty_remarks, verified_by, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                ('Full Stack Web Internship Certificate', 'Rahul Verma', 'rahul@campus.edu', '21IT019',
                 'Internship', 'TechCorp Innovations', '2026-01-20', '',
                 'sample-aws-cert.pdf', 'pdf', 'Rejected', 'Certificate missing company seal and HR signature. Please upload an official signed copy.',
                 'faculty@campus.edu', datetime.now().strftime('%Y-%m-%d %H:%M')))

        conn.commit()
        conn.close()
    else:
        # Aurora MySQL Mode
        c = db()
        with c.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS users (
                email VARCHAR(150) PRIMARY KEY,
                password_hash VARCHAR(255),
                full_name VARCHAR(150),
                role VARCHAR(50) DEFAULT 'student',
                roll_number VARCHAR(50),
                department VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

            cur.execute('''CREATE TABLE IF NOT EXISTS certificates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                student_name VARCHAR(150) NOT NULL,
                student_email VARCHAR(150) NOT NULL,
                roll_number VARCHAR(50),
                category VARCHAR(100),
                issuing_org VARCHAR(150),
                issue_date VARCHAR(50),
                credential_url VARCHAR(300),
                s3_key VARCHAR(400) NOT NULL,
                file_type VARCHAR(20) DEFAULT 'pdf',
                status VARCHAR(50) DEFAULT 'Pending',
                faculty_remarks TEXT,
                verified_by VARCHAR(150),
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP NULL)''')
        c.close()


try:
    init_db()
except Exception as e:
    log.error('DB init failed: %s', e)


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return wrapper


def faculty_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'faculty':
            flash('Access restricted to faculty members.')
            return redirect(url_for('index'))
        return f(*a, **k)
    return wrapper


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/health')
def health():
    return 'OK'  # AWS Application Load Balancer health check


# --- Authentication Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip() or email.split('@')[0].capitalize()
        role = request.form.get('role', 'student').strip().lower()
        roll_number = request.form.get('roll_number', '').strip().upper()
        department = request.form.get('department', '').strip()

        if role not in ('student', 'faculty'):
            role = 'student'

        if IS_LOCAL:
            conn = get_local_db()
            try:
                conn.execute(
                    '''INSERT INTO users (email, password_hash, full_name, role, roll_number, department)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (email, generate_password_hash(password), full_name, role, roll_number, department)
                )
                conn.commit()
                log.info('Local signup: %s (%s)', email, role)
                flash(f'Account created successfully as {role.capitalize()}! Please log in.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('An account with that email already exists.')
        else:
            try:
                # AWS Cognito Signup
                cog.sign_up(
                    ClientId=CLIENT_ID,
                    Username=email,
                    Password=password,
                    UserAttributes=[
                        {'Name': 'email', 'Value': email},
                        {'Name': 'name', 'Value': full_name}
                    ]
                )
                cog.admin_confirm_sign_up(UserPoolId=POOL_ID, Username=email)

                # Store user profile in Aurora
                c = db()
                with c.cursor() as cur:
                    cur.execute(
                        '''INSERT INTO users (email, full_name, role, roll_number, department)
                           VALUES (%s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE full_name=%s, role=%s, roll_number=%s, department=%s''',
                        (email, full_name, role, roll_number, department,
                         full_name, role, roll_number, department)
                    )
                c.close()

                log.info('AWS Cognito signup: %s (%s)', email, role)
                flash(f'Account created successfully as {role.capitalize()}! Please log in.')
                return redirect(url_for('login'))
            except ClientError as e:
                flash(e.response['Error']['Message'])
            except Exception as e:
                flash(f'Signup error: {str(e)}')

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if IS_LOCAL:
            conn = get_local_db()
            row = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if row and check_password_hash(row['password_hash'], password):
                session['user'] = email
                session['name'] = row['full_name'] or email.split('@')[0].capitalize()
                session['role'] = row['role'] or 'student'
                session['roll_number'] = row['roll_number'] or ''
                session['department'] = row['department'] or ''
                log.info('Local login: %s (%s)', email, session['role'])
                flash(f'Welcome back, {session["name"]}!')
                return redirect(url_for('index'))
            flash('Invalid email or password.')
        else:
            try:
                cog.initiate_auth(
                    ClientId=CLIENT_ID,
                    AuthFlow='USER_PASSWORD_AUTH',
                    AuthParameters={'USERNAME': email, 'PASSWORD': password}
                )

                # Fetch profile from Aurora
                c = db()
                with c.cursor() as cur:
                    cur.execute('SELECT * FROM users WHERE email=%s', (email,))
                    row = cur.fetchone()
                c.close()

                session['user'] = email
                if row:
                    session['name'] = row.get('full_name') or email.split('@')[0].capitalize()
                    session['role'] = row.get('role', 'student')
                    session['roll_number'] = row.get('roll_number', '')
                    session['department'] = row.get('department', '')
                else:
                    session['name'] = email.split('@')[0].capitalize()
                    session['role'] = 'student'

                log.info('AWS login: %s (%s)', email, session['role'])
                flash(f'Welcome back, {session["name"]}!')
                return redirect(url_for('index'))
            except ClientError as e:
                flash(e.response['Error']['Message'])
            except Exception as e:
                flash(f'Authentication error: {str(e)}')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out safely.')
    return redirect(url_for('login'))


@app.route('/switch-role')
@login_required
def switch_role():
    """Allows instant toggling between Student and Faculty mode for demo and evaluation."""
    current = session.get('role', 'student')
    new_role = 'faculty' if current == 'student' else 'student'
    session['role'] = new_role

    # Update in database if local
    if IS_LOCAL:
        try:
            conn = get_local_db()
            conn.execute('UPDATE users SET role=? WHERE email=?', (new_role, session['user']))
            conn.commit()
        except Exception:
            pass

    flash(f'Switched active view to {new_role.upper()} Mode.')
    return redirect(url_for('index'))


# --- Main Dashboard & Faculty Views ---
@app.route('/')
@login_required
def index():
    user = session['user']
    role = session.get('role', 'student')

    if role == 'faculty':
        return redirect(url_for('faculty_portal'))

    # Student Dashboard: Shows their uploaded certificates
    if IS_LOCAL:
        conn = get_local_db()
        certs = conn.execute(
            '''SELECT * FROM certificates WHERE student_email=? ORDER BY id DESC''',
            (user,)
        ).fetchall()
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute(
                '''SELECT * FROM certificates WHERE student_email=%s ORDER BY id DESC''',
                (user,)
            )
            certs = cur.fetchall()
        c.close()

    # Calculate summary counts for student
    total_count = len(certs)
    approved_count = sum(1 for c in certs if c['status'] == 'Approved')
    pending_count = sum(1 for c in certs if c['status'] == 'Pending')
    rejected_count = sum(1 for c in certs if c['status'] == 'Rejected')

    stats = {
        'total': total_count,
        'approved': approved_count,
        'pending': pending_count,
        'rejected': rejected_count
    }

    return render_template('index.html', certs=certs, stats=stats)


@app.route('/faculty')
@login_required
def faculty_portal():
    """Faculty Review Portal: displays all student certificates with filters."""
    # Ensure current role is faculty
    if session.get('role') != 'faculty':
        flash('Faculty portal view enabled.')
        session['role'] = 'faculty'

    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    search_query = request.args.get('q', '').strip().lower()

    if IS_LOCAL:
        conn = get_local_db()
        all_certs = conn.execute(
            '''SELECT * FROM certificates ORDER BY id DESC'''
        ).fetchall()
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute('''SELECT * FROM certificates ORDER BY id DESC''')
            all_certs = cur.fetchall()
        c.close()

    # Calculate global faculty metrics
    total_count = len(all_certs)
    pending_count = sum(1 for c in all_certs if c['status'] == 'Pending')
    approved_count = sum(1 for c in all_certs if c['status'] == 'Approved')
    rejected_count = sum(1 for c in all_certs if c['status'] == 'Rejected')

    filtered_certs = []
    for c in all_certs:
        # Status filter
        if status_filter != 'all' and c['status'].lower() != status_filter.lower():
            continue
        # Category filter
        if category_filter != 'all' and (c['category'] or '').lower() != category_filter.lower():
            continue
        # Search query matching
        if search_query:
            match_fields = [
                c['title'] or '',
                c['student_name'] or '',
                c['student_email'] or '',
                c['roll_number'] or '',
                c['issuing_org'] or '',
                c['category'] or ''
            ]
            if not any(search_query in field.lower() for field in match_fields):
                continue
        filtered_certs.append(c)

    stats = {
        'total': total_count,
        'pending': pending_count,
        'approved': approved_count,
        'rejected': rejected_count
    }

    return render_template(
        'faculty.html',
        certs=filtered_certs,
        stats=stats,
        current_status=status_filter,
        current_category=category_filter,
        search_query=search_query
    )


# --- Certificate Upload, Verification & File Handlers ---
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    f = request.files.get('file')
    if not f or not f.filename:
        flash('Please select a certificate file (PDF, PNG, or JPG).')
        return redirect(url_for('index'))

    if not allowed_file(f.filename):
        flash('Invalid file format. Only PDF, PNG, and JPG files are supported.')
        return redirect(url_for('index'))

    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Technical Certification').strip()
    issuing_org = request.form.get('issuing_org', '').strip()
    issue_date = request.form.get('issue_date', '').strip()
    credential_url = request.form.get('credential_url', '').strip()
    roll_number = request.form.get('roll_number', session.get('roll_number', '')).strip()
    student_name = request.form.get('student_name', session.get('name', '')).strip()

    ext = f.filename.rsplit('.', 1)[1].lower()
    file_type = 'pdf' if ext == 'pdf' else 'image'
    unique_filename = f"{uuid.uuid4().hex[:12]}_{secure_filename(f.filename)}"

    if IS_LOCAL:
        local_path = os.path.join(UPLOAD_DIR, unique_filename)
        f.save(local_path)
        key = unique_filename

        conn = get_local_db()
        conn.execute('''INSERT INTO certificates 
            (title, student_name, student_email, roll_number, category, issuing_org, 
             issue_date, credential_url, s3_key, file_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')''',
            (title, student_name, session['user'], roll_number, category, issuing_org,
             issue_date, credential_url, key, file_type))
        conn.commit()
    else:
        s3_key = f"certificates/{unique_filename}"
        content_type = 'application/pdf' if file_type == 'pdf' else f'image/{ext}'
        s3.upload_fileobj(
            f, BUCKET, s3_key,
            ExtraArgs={'ContentType': content_type}
        )
        key = s3_key

        c = db()
        with c.cursor() as cur:
            cur.execute('''INSERT INTO certificates 
                (title, student_name, student_email, roll_number, category, issuing_org, 
                 issue_date, credential_url, s3_key, file_type, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')''',
                (title, student_name, session['user'], roll_number, category, issuing_org,
                 issue_date, credential_url, key, file_type))
        c.close()

    log.info('Certificate uploaded: %s by %s', title, session['user'])
    flash('Certificate uploaded successfully! Submitted for Faculty Verification.')
    return redirect(url_for('index'))


@app.route('/verify/<int:cid>', methods=['POST'])
@faculty_required
def verify_certificate(cid):
    """Action endpoint for faculty to Approve or Reject a student's certificate."""
    action = request.form.get('action', '').strip().lower()
    remarks = request.form.get('remarks', '').strip()

    if action not in ('approve', 'reject'):
        flash('Invalid verification action.')
        return redirect(url_for('faculty_portal'))

    new_status = 'Approved' if action == 'approve' else 'Rejected'
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    faculty_user = session.get('name') or session['user']

    if not remarks:
        if new_status == 'Approved':
            remarks = 'Verified authentic credential. Approved for academic credit.'
        else:
            remarks = 'Certificate could not be verified. Please check details and resubmit.'

    if IS_LOCAL:
        conn = get_local_db()
        conn.execute('''UPDATE certificates 
            SET status=?, faculty_remarks=?, verified_by=?, verified_at=?
            WHERE id=?''',
            (new_status, remarks, faculty_user, now_str, cid))
        conn.commit()
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute('''UPDATE certificates 
                SET status=%s, faculty_remarks=%s, verified_by=%s, verified_at=%s
                WHERE id=%s''',
                (new_status, remarks, faculty_user, now_str, cid))
        c.close()

    log.info('Certificate %s %s by %s', cid, new_status, session['user'])
    flash(f'Certificate marked as {new_status}. Remarks saved for student.')
    return redirect(request.referrer or url_for('faculty_portal'))


@app.route('/view/<int:cid>')
@login_required
def view_certificate(cid):
    """View certificate document in browser (PDF or Image)."""
    if IS_LOCAL:
        conn = get_local_db()
        cert = conn.execute('SELECT * FROM certificates WHERE id=?', (cid,)).fetchone()
        if not cert:
            return 'Certificate not found', 404

        # Access check: student can only view own; faculty can view all
        if session.get('role') != 'faculty' and cert['student_email'] != session['user']:
            flash('Access unauthorized.')
            return redirect(url_for('index'))

        filename = os.path.basename(cert['s3_key'])
        return send_from_directory(UPLOAD_DIR, filename)
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute('SELECT * FROM certificates WHERE id=%s', (cid,))
            cert = cur.fetchone()
        c.close()

        if not cert:
            return 'Certificate not found', 404

        if session.get('role') != 'faculty' and cert['student_email'] != session['user']:
            flash('Access unauthorized.')
            return redirect(url_for('index'))

        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET, 'Key': cert['s3_key'], 'ResponseContentDisposition': 'inline'},
            ExpiresIn=300
        )
        return redirect(url)


@app.route('/download/<int:cid>')
@login_required
def download_certificate(cid):
    """Download certificate file with forced attachment disposition."""
    if IS_LOCAL:
        conn = get_local_db()
        cert = conn.execute('SELECT * FROM certificates WHERE id=?', (cid,)).fetchone()
        if not cert:
            return 'Certificate not found', 404

        if session.get('role') != 'faculty' and cert['student_email'] != session['user']:
            flash('Access unauthorized.')
            return redirect(url_for('index'))

        filename = os.path.basename(cert['s3_key'])
        return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute('SELECT * FROM certificates WHERE id=%s', (cid,))
            cert = cur.fetchone()
        c.close()

        if not cert:
            return 'Certificate not found', 404

        if session.get('role') != 'faculty' and cert['student_email'] != session['user']:
            flash('Access unauthorized.')
            return redirect(url_for('index'))

        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET, 'Key': cert['s3_key'], 'ResponseContentDisposition': 'attachment'},
            ExpiresIn=300
        )
        return redirect(url)


@app.route('/delete/<int:cid>', methods=['POST'])
@login_required
def delete_certificate(cid):
    """Students can delete pending or rejected certificates."""
    if IS_LOCAL:
        conn = get_local_db()
        cert = conn.execute('SELECT * FROM certificates WHERE id=?', (cid,)).fetchone()
        if not cert:
            flash('Certificate not found.')
            return redirect(url_for('index'))

        if cert['student_email'] != session['user'] and session.get('role') != 'faculty':
            flash('Permission denied.')
            return redirect(url_for('index'))

        if cert['status'] == 'Approved' and session.get('role') != 'faculty':
            flash('Approved certificates cannot be deleted. Contact faculty if changes are required.')
            return redirect(url_for('index'))

        try:
            filename = os.path.basename(cert['s3_key'])
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            log.warning('Could not delete local file: %s', e)

        conn.execute('DELETE FROM certificates WHERE id=?', (cid,))
        conn.commit()
    else:
        c = db()
        with c.cursor() as cur:
            cur.execute('SELECT * FROM certificates WHERE id=%s', (cid,))
            cert = cur.fetchone()
            if not cert:
                c.close()
                flash('Certificate not found.')
                return redirect(url_for('index'))

            if cert['student_email'] != session['user'] and session.get('role') != 'faculty':
                c.close()
                flash('Permission denied.')
                return redirect(url_for('index'))

            if cert['status'] == 'Approved' and session.get('role') != 'faculty':
                c.close()
                flash('Approved certificates cannot be deleted. Contact faculty if changes are required.')
                return redirect(url_for('index'))

            try:
                s3.delete_object(Bucket=BUCKET, Key=cert['s3_key'])
            except Exception as e:
                log.warning('Could not delete S3 object: %s', e)

            cur.execute('DELETE FROM certificates WHERE id=%s', (cid,))
        c.close()

    flash('Certificate record removed.')
    return redirect(request.referrer or url_for('index'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=IS_LOCAL)
