# 🩺 MediScribe — Generative AI–Powered Clinical Documentation Assistant

MediScribe is a secure, state-of-the-art **Generative AI Healthcare SaaS platform** designed to eliminate clinical documentation burnout. It captures live doctor-patient consultations, performs real-time speech transcription, synchronizes conversations bidirectionally, and automatically generates structured clinical records (**SOAP Notes**, **Prescriptions**, **EHR updates**, **Patient Visit Summaries**, and **FHIR/HL7 JSON entries**).

---

## 🌟 Key Features

### 1. 🔄 Bidirectional Live Consultation & Synchronization
- **Two-Way Initiation:** Consultations can be initiated either by the **Doctor** (selecting an existing/new patient) or by the **Patient** (selecting their preferred Doctor and Department).
- **Instant Notification Alerts:** When either party starts a consultation or sends a message, the counterparty receives a real-time toast alert banner with an audio chime and direct one-click room navigation.
- **Synchronized Audio & Chat Streams:** Real-time polling synchronization (sub-2s latency) ensures messages, transcribed speech, and clinical notes reflect synchronously on both the **Doctor's Clinical Workspace** and the **Patient's Interactive Consultation Room**.
- **Live Speech Transcription:** Supports browser-native **Web Speech Recognition** as well as high-accuracy **Groq Whisper (`whisper-large-v3`)** audio uploads with audio waveform visualizers.

### 2. ⚡ Generative AI Clinical Documentation Engine
- **Automated SOAP Notes:** Generates Subjective, Objective, Assessment, and Plan notes instantly from conversation transcripts.
- **Digital Prescriptions & Patient Summaries:** Produces structured medication charts (drug name, dosage, frequency, duration) and plain-language summaries for patients.
- **FHIR / HL7 Interoperability:** Generates standard JSON schemas for seamless EHR/EMR export.
- **Customizable Prompts:** System administrators can fine-tune LLM system prompts directly from the administration dashboard.
- **Multi-Format Export:** One-click download of clinical notes in **PDF**, **DOCX**, **TXT**, and **JSON**.

### 3. 🤖 Global Action-Based AI Copilot
- **Floating AI Assistant:** Available on every page for authenticated users.
- **Clinical Intelligence:** Queries diagnostic definitions, ICD-10 medical coding, drug interaction checks, and patient-friendly report rewrites powered by Groq LLMs.

### 4. 👥 Role-Based Portals & Dashboards
- **Doctor / Clinician Portal:** Comprehensive workspace with real-time waveform recording, transcript editor, AI generation panel, document review, and patient history.
- **Patient Portal:** Interactive consultation room, digital visit timeline, chronic condition tracker, and instant access to prescriptions and discharge notes.
- **Admin & Compliance Panel:** Audit logs, prompt configuration management, and system security monitors.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11+, Django 5.x / 4.2+, Django REST Framework |
| **AI / LLM Integration** | Groq API (`llama-3.3-70b-versatile`, `whisper-large-v3`, `openai/gpt-oss-120b`) |
| **Database** | MySQL 8.0 (Production) / SQLite (Development & Local Evaluation) |
| **Frontend** | HTML5, Vanilla CSS3 (Custom Theme: Teal `#078A83`, Navy `#07152D`, Mint `#67DDE0`), ES6+ JavaScript |
| **Audio & Speech** | Web Audio API (Waveform Canvas), Web Speech API, MediaRecorder API |
| **UI Libraries** | Bootstrap 5, FontAwesome 6, Chart.js, GSAP 3.12, AOS (Animate On Scroll) |
| **Export Engines** | ReportLab (PDF), python-docx (DOCX), JSON Serialization |

---

## 📂 Project Architecture

```
MediScribe/
├── authentication/        # User authentication, role-based views (Doctor/Patient), profiles
├── consultations/         # Consultation lifecycle, live room, doctor workspace, sync & notifications
│   ├── models.py          # Consultation, ConsultationMessage, ClinicalDocument, Notification
│   ├── views.py           # Room rendering, message dispatch, delta sync, document export
│   └── urls.py            # Consultation routing
├── core/                  # Dashboards (Doctor/Patient/Admin), audit logging, prompt configs
├── api/                   # RESTful API endpoints for external integrations
├── mediscribe/            # Core Django project settings, WSGI/ASGI configuration
├── templates/             # Premium responsive UI templates
│   ├── base.html          # Global layout, toast alerts, notification poller, AI widget
│   ├── consultations/     # Consultation room, workspace, new consultation, list view
│   ├── dashboard/         # Doctor, Patient, and Admin dashboard views & timelines
│   └── auth/              # Login, patient login, and registration templates
├── tests/                 # Automated unit and integration test suite
├── seed_db.py             # Database seeder with sample doctors, patients, and prompts
├── requirements.txt       # Python dependencies
└── manage.py              # Django management script
```

---

## 🚀 Quick Start Guide

### 1. Clone & Setup Virtual Environment
```bash
# Clone the repository
git clone <repository_url>
cd "MediScribe Generative AI–Powered Clinical Documentation Assistant"

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory (optional if using defaults):
```env
DEBUG=True
SECRET_KEY=your-secret-key-here
GROQ_API_KEY=your-groq-api-key-here
# Optional MySQL Configuration (falls back to SQLite if not provided):
# DB_NAME=mediscribe_db
# DB_USER=root
# DB_PASSWORD=yourpassword
# DB_HOST=127.0.0.1
# DB_PORT=3306
```

### 4. Run Migrations & Seed Database
```bash
python manage.py makemigrations authentication consultations core api
python manage.py migrate

# Seed sample users, doctors, patients, and AI prompt templates
python seed_db.py
```

### 5. Run the Development Server
```bash
python manage.py runserver
```
Access the application at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## 🔑 Default Test Accounts

| Role | Username | Password | Dashboard URL |
|---|---|---|---|
| **Doctor** | `doctor` | `doctor123` | `/dashboard/` |
| **Patient** | `patient` | `patient123` | `/dashboard/` |
| **System Admin** | `admin` | `admin` | `/dashboard/` |

---

## 📡 Key API & Synchronization Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/consultations/new/` | `GET`, `POST` | Role-adaptive consultation initiation (Doctor/Patient) |
| `/consultations/<id>/room/` | `GET` | Live Patient Consultation Room with audio visualizer |
| `/consultations/<id>/workspace/` | `GET` | Doctor Clinical Workspace with transcript & AI tools |
| `/consultations/<id>/send-message/` | `POST` | Send dialogue / speech transcript with counterparty notification |
| `/consultations/<id>/sync/` | `GET` | Real-time delta sync for messages, transcript & documents |
| `/consultations/notifications/unread/`| `GET` | Global real-time unread notification poller |
| `/consultations/notifications/mark-read/` | `POST` | Mark notification as read |
| `/consultations/<id>/workspace/process/` | `POST` | Trigger Generative AI document creation (SOAP/Prescription) |
| `/consultations/document/<id>/export/<format>/` | `GET` | Export clinical documents (`pdf`, `docx`, `txt`, `json`) |

---

## 🧪 Automated Testing

Run the automated test suite to verify consultation creation, bidirectional messaging, access control, and notification dispatches:

```bash
python manage.py test tests.test_consultation_sync --noinput
```

All 5 core synchronization test cases run against a clean test database and validate:
- ✅ Doctor-initiated consultation flow
- ✅ Patient-initiated consultation flow
- ✅ Real-time bidirectional message synchronization
- ✅ Unauthorized room/workspace access prevention
- ✅ Real-time notification dispatch and polling

---

## 🔒 Security & Compliance Design
- **Role-Based Access Control (RBAC):** Strict view decorators ensuring patients cannot access doctor workspaces or other patients' consultation rooms.
- **Audit Logging:** Every consultation lifecycle event, message dispatch, and AI document generation is recorded with user identity, timestamp, and IP address.
- **Data Protection:** CSRF-protected POST requests, SQL injection prevention via Django ORM, and safe XSS-escaped rendering.

---

## 📄 License
This project is developed for clinical documentation workflows and healthcare AI research. Distributed under the MIT License.
