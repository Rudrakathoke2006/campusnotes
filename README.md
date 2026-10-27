# 🎓 CampusNotes & CampusCert Portal

[![CI/CD Test Pipeline](https://github.com/Rudrakathoke2006/campusnotes/actions/workflows/ci.yml/badge.svg)](https://github.com/Rudrakathoke2006/campusnotes/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A scalable, multi-tier academic certificate verification and study notes repository platform engineered for modern cloud infrastructure (AWS) and local emulation.

---

## 🚀 Fast Deployment Options

### Option 1: 1-Click Deploy to Render (Fastest & Free)
Deploy immediately with a free live HTTPS URL and zero AWS costs:

1. Click **Deploy to Render**:
   [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
2. Connect your GitHub repository: `Rudrakathoke2006/campusnotes`.
3. Render automatically detects `render.yaml` and deploys using `gunicorn wsgi:app`.
4. Your live app is accessible at `https://campusnotes-xxxx.onrender.com` in ~2 minutes!

---

### Option 2: Run with Docker Anywhere
```bash
# Build the image
docker build -t campusnotes .

# Run the container locally or on any cloud server
docker run -p 8000:8000 campusnotes
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

---

### Option 3: Full Production Deployment on AWS
Designed for AWS Cloud Architecture with:
- **Application Load Balancer (ALB)** with Auto Scaling across multi-AZ
- **Amazon Aurora MySQL** managed database with Secrets Manager
- **Amazon S3** secure document storage with presigned URLs & lifecycle rules
- **Amazon Cognito** user pool authentication
- **Amazon EFS** shared file storage for system-wide announcements
- **AWS Lambda & Amazon SNS** asynchronous notification processing
- **Amazon CloudWatch** logging and metrics

Run deployment from AWS CloudShell (`ap-south-1`):
```bash
cd campusnotes-project/aws
bash 00_setup.sh
bash 01_network.sh
# Follow instructions in campusnotes-project/README.md for DB, services, and launch
bash 02_services.sh your-email@example.com
bash 03_build_and_upload.sh
bash 04_iam.sh && bash 05_efs.sh && bash 06_launch.sh
```

---

## 🔑 Demo Credentials (Local / Cloud Demo Mode)

When running in Local Mode or Cloud Container mode, seed credentials are automatically populated:

| Role | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Student** | `student@campus.edu` | `Campus@123` | Upload, view, manage, and download certificates & notes |
| **Faculty / Evaluator** | `faculty@campus.edu` | `Campus@123` | Review, approve, reject with remarks, campus broadcast |

---

## 💻 Local Quickstart

```bash
# 1. Clone repository
git clone https://github.com/Rudrakathoke2006/campusnotes.git
cd campusnotes

# 2. Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start local development server
python wsgi.py
```
Visit [http://localhost:8000](http://localhost:8000).

---

## 🧪 Automated Testing

All 19 white-box and integration unit tests run via pytest:

```bash
pytest -v
```

```text
============================= test session starts =============================
collected 19 items

tests/test_app.py::test_is_pdf_validation PASSED                         [  5%]
tests/test_app.py::test_signup_get_page PASSED                           [ 10%]
tests/test_app.py::test_signup_success PASSED                            [ 15%]
tests/test_app.py::test_signup_duplicate_email_error PASSED              [ 21%]
tests/test_app.py::test_login_get_page PASSED                            [ 26%]
tests/test_app.py::test_login_success PASSED                             [ 31%]
tests/test_app.py::test_login_invalid_password PASSED                    [ 36%]
tests/test_app.py::test_login_unregistered_email PASSED                  [ 42%]
tests/test_app.py::test_login_required_protected_routes PASSED           [ 47%]
tests/test_app.py::test_logout PASSED                                    [ 52%]
tests/test_app.py::test_dashboard_empty_repository PASSED                [ 57%]
tests/test_app.py::test_upload_note_pdf_success PASSED                   [ 63%]
tests/test_app.py::test_upload_note_invalid_file_rejected PASSED         [ 68%]
tests/test_app.py::test_replace_note_own_file_success PASSED              [ 73%]
tests/test_app.py::test_replace_note_other_user_forbidden PASSED         [ 78%]
tests/test_app.py::test_download_note_success PASSED                     [ 84%]
tests/test_app.py::test_download_nonexistent_note_404 PASSED             [ 89%]
tests/test_app.py::test_announcement_banner_display PASSED              [ 94%]
tests/test_app.py::test_health_check_endpoint PASSED                     [100%]

============================= 19 passed in 10.82s =============================
```

---

## 📂 Project Architecture

```
├── app/                      # Main Flask application & UI
│   ├── app.py                # Core application routes & logic
│   ├── static/style.css      # Responsive CSS design system
│   ├── templates/            # Jinja2 templates (login, signup, base, faculty, etc.)
│   └── uploads/              # Local upload storage (emulation)
├── aws/                      # AWS automation scripts (ALB, ASG, S3, RDS, EFS, Lambda)
├── stages/                   # Incremental lab stages (Stage 1 to Stage 3)
├── tests/                    # Pytest test suite (19 test cases)
├── Dockerfile                # Multi-stage production container
├── Procfile                  # Gunicorn web process definition
├── render.yaml               # Render Cloud Blueprint
├── wsgi.py                   # Production WSGI entry point
└── requirements.txt          # Python dependencies
```
