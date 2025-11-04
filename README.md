# Patient Consent Management System

A secure, AI-powered platform for managing and querying medical consent forms with patient-specific authentication and access control.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## ✨ Features

- 🔒 **Secure Patient Authentication**: Auto-generated accounts with password hashing
- 🔍 **AI-Powered OCR**: Google Cloud Vision API for accurate PDF text extraction  
- 🧠 **Intelligent Analysis**: Google Gemini 2.0 Flash for structured data extraction
- 💬 **Natural Language Queries**: Ask questions about consent forms in plain English
- 🛡️ **Patient Data Isolation**: Each patient can only access their own consent forms
- 🎨 **Beautiful UI**: Modern, responsive patient portal with gradient animations
- ⚡ **Auto-Scaling**: Cloud Run and Cloud Functions auto-scale based on demand

## 🎯 Project Overview

This system automatically processes PDF consent forms uploaded to Google Cloud Storage, extracts patient information using advanced OCR and AI models, and provides a secure patient portal where patients can query their own consent forms using natural language.

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    END-TO-END WORKFLOW                          │
└─────────────────────────────────────────────────────────────────┘

1. EHR System UPLOADS PDF
   │
   ▼
┌─────────────────────────────────┐
│  Cloud Storage Bucket           │
│  consent-management-            │
│  summarizer-bucket              │
└──────────────┬──────────────────┘
               │
               │ (Triggers on file upload)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  INGESTION FUNCTION (Cloud Functions Gen 2)                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Step 1: OCR Processing                                    │ │
│  │   • Google Cloud Vision API                               │ │
│  │   • Document Text Detection                               │ │
│  │   • Extracts text from PDF pages                          │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Step 2: AI Analysis                                       │ │
│  │   • Google Gemini 2.0 Flash (gemini-2.0-flash-exp)        │ │
│  │   • Extracts: patient name, email, DOB, doctor, procedure │ │
│  │   • Identifies: consented items, declined items          │ │
│  │   • Generates: summary and structured JSON                │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Step 3: Data Storage                                      │ │
│  │   • Stores in Firestore 'consents' collection            │ │
│  │   • Stores in Firestore 'entity_index' collection         │ │
│  │   • Creates patient account in 'patients' collection      │ │
│  │   • Auto-generates password: {firstname}123!              │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  FIRESTORE DATABASE (consent-management-db)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  patients   │  │  consents    │  │   entity_index      │ │
│  │  Collection │  │  Collection  │  │   Collection        │ │
│  │             │  │              │  │                      │ │
│  │ • email     │  │ • filename   │  │ • patient_email     │ │
│  │ • password  │  │ • full_text  │  │ • patient_name      │ │
│  │ • name      │  │ • ai_analysis│  │ • consented_items   │ │
│  │             │  │              │  │ • declined_items    │ │
│  │             │  │              │  │ • summary           │ │
│  │             │  │              │  │ • entities           │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
               │
               │ (Patient queries)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PATIENT PORTAL (Frontend - Cloud Run)                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ • Login Interface (email + password)                      │ │
│  │ • Beautiful UI with gradient animations                   │ │
│  │ • Natural Language Query Input                            │ │
│  │ • Real-time AI Responses                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
└──────────────┬─────────────────────────────────────────────────┘
               │
               │ (Authenticated API calls)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  QUERY SERVICE API (Flask - Cloud Run)                         │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Authentication:                                          │ │
│  │   • SHA-256 password hashing                              │ │
│  │   • Session token management (8-hour expiration)          │ │
│  │   • Patient email verification                            │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Query Processing:                                         │ │
│  │   1. Validates session token                              │ │
│  │   2. Queries Firestore by patient_email only              │ │
│  │   3. Passes patient's documents to AI                     │ │
│  │   4. Gemini 2.0 Flash generates contextual answer         │ │
│  │   5. Returns answer restricted to patient's data          │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  RESPONSE TO PATIENT                                            │
│  • Secure, patient-specific answers                             │
│  • No cross-patient data access                                 │
│  • HIPAA-compliant design                                       │
└─────────────────────────────────────────────────────────────────┘
```

## 🤖 AI Models Used

### 1. Google Cloud Vision API
**Purpose**: OCR (Optical Character Recognition) for PDF text extraction

**Model**: Document Text Detection
- **Type**: Batch async annotation
- **Input**: PDF files from Cloud Storage
- **Output**: Extracted text from all PDF pages
- **Features**:
  - Handles multi-page PDFs
  - Preserves text layout and structure
  - Supports various PDF formats

**Usage**:
```python
from google.cloud import vision

vision_client = vision.ImageAnnotatorClient()
feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
async_request = vision.AsyncAnnotateFileRequest(...)
operation = vision_client.async_batch_annotate_files(requests=[async_request])
```

### 2. Google Gemini 2.0 Flash (Experimental)
**Purpose**: Intelligent analysis and extraction of structured data from consent forms

**Model**: `gemini-2.0-flash-exp`
- **Type**: Large Language Model (Generative AI)
- **Input**: OCR-extracted text from consent forms
- **Output**: Structured JSON with:
  - Patient entities (name, email, DOB, doctor, procedure, date)
  - Consented items (list)
  - Declined items (list)
  - Summary (paragraph)
  - Patient ID (for authentication)

**Why Gemini 2.0 Flash?**
- Superior structured data extraction from OCR text
- Better understanding of medical terminology
- Handles incomplete or noisy OCR output
- Fast inference time
- Cost-effective for batch processing

**Usage**:
```python
import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.0-flash-exp")
response = model.generate_content(prompt)
```

**Prompt Engineering**:
- Structured JSON output format
- Entity extraction instructions
- Medical terminology understanding
- Error handling for missing data

### 3. Google Gemini 2.0 Flash (Query Processing)
**Purpose**: Natural language understanding and generation for patient queries

**Model**: `gemini-2.0-flash-exp`
- **Type**: Large Language Model (Generative AI)
- **Input**: Patient's natural language question + their consent form data
- **Output**: Human-readable, contextual answer

**Features**:
- Understands medical consent terminology
- Generates patient-friendly responses
- Enforces security rules (only patient's data)
- Context-aware responses

**Security Constraints in Prompt**:
- Only discuss patient's own consent forms
- Never mention other patients
- Politely decline cross-patient queries
- HIPAA-compliant responses

## 🔄 Complete End-to-End Workflow

### Phase 1: PDF Processing (Automatic)

1. **Administrator uploads PDF** to Cloud Storage bucket
   ```bash
   gcloud storage cp consent.pdf gs://consent-management-summarizer-bucket/
   ```

2. **Cloud Function triggers** automatically on file upload

3. **Vision API processes PDF**:
   - Extracts text from all pages
   - Handles multi-page documents
   - Preserves text structure

4. **Gemini 2.0 Flash analyzes text**:
   - Extracts patient information (name, email, DOB)
   - Identifies doctor and procedure
   - Lists consented items
   - Lists declined items
   - Generates summary

5. **Data stored in Firestore**:
   - `consents` collection: Raw OCR text and AI analysis
   - `entity_index` collection: Structured, searchable data
   - `patients` collection: Auto-created account with default password

6. **Patient account created**:
   - Email: From consent form
   - Password: `{firstname}123!` (e.g., `john123!`)
   - Password hash: SHA-256 stored in Firestore

### Phase 2: Patient Access (On-Demand)

1. **Patient visits portal**:
   ```
   https://consent-patient-portal-59175121751.us-central1.run.app
   ```

2. **Patient logs in**:
   - Email: From their consent form
   - Password: `{firstname}123!`

3. **Session created**:
   - SHA-256 password verification
   - Session token generated (8-hour expiration)
   - Token stored in frontend localStorage

4. **Patient asks question**:
   - Natural language input (e.g., "What did I consent to?")
   - Query sent to API with session token

5. **Query service processes**:
   - Validates session token
   - Queries Firestore `entity_index` by `patient_email` only
   - Retrieves only patient's own consent forms
   - Passes data to Gemini 2.0 Flash

6. **AI generates answer**:
   - Gemini 2.0 Flash receives patient's question + their consent data
   - Generates contextual, patient-friendly answer
   - Enforces security: only discusses patient's data

7. **Response displayed**:
   - Answer shown in beautiful UI
   - Patient can ask follow-up questions
   - All queries remain patient-specific

## 🏗️ System Components

### 1. Ingestion Function (`ingestion-function/main.py`)
**Deployment**: Google Cloud Functions Gen 2  
**Runtime**: Python 3.11  
**Trigger**: Cloud Storage bucket uploads  
**Memory**: 1GB  
**Timeout**: 540 seconds

**Key Functions**:
- `process_consent_pdf()`: Main entry point, triggered by bucket uploads
- `_store_enhanced_analysis()`: Stores structured data in entity_index
- `_create_patient_account()`: Auto-creates patient accounts

**Models Used**:
- Google Cloud Vision API (OCR)
- Gemini 2.0 Flash Experimental (Analysis)

### 2. Query Service (`query-service/app.py`)
**Deployment**: Google Cloud Run  
**Framework**: Flask  
**Memory**: 2GB  
**CPU**: 2 vCPU  
**Timeout**: 300 seconds

**Endpoints**:
- `POST /login`: Patient authentication
- `POST /logout`: Session termination
- `POST /query`: Patient query processing (requires auth)
- `GET /health`: Health check

**Models Used**:
- Gemini 2.0 Flash Experimental (Query processing)

**Security**:
- SHA-256 password hashing
- Session token validation
- Patient email filtering on all queries

### 3. Patient Portal (`frontend/index.html`)
**Deployment**: Google Cloud Run  
**Framework**: Vanilla JavaScript + HTML/CSS  
**Memory**: 512MB  
**CPU**: 1 vCPU

**Features**:
- Beautiful login interface
- Patient dashboard
- Natural language query input
- Real-time AI responses
- Responsive design

## 📊 Firestore Database Structure

### Collection: `patients`
Patient authentication accounts
```json
{
  "email": "john.smith@example.com",
  "password_hash": "sha256_hash",
  "patient_name": "John Smith",
  "default_password": "john123!",
  "created_at": "2024-11-03T00:00:00Z"
}
```

### Collection: `consents`
Raw consent form data
```json
{
  "filename": "consent_123.pdf",
  "full_text": "OCR extracted text...",
  "ai_analysis_json": "{...}",
  "processed_timestamp": "2024-11-03T00:00:00Z"
}
```

### Collection: `entity_index`
Structured, searchable consent data (used for queries)
```json
{
  "document_id": "consent_123",
  "patient_name": "John Smith",
  "patient_email": "john.smith@example.com",
  "patient_id": "john_smith_001",
  "consented_items": ["Surgery", "Anesthesia"],
  "declined_items": ["Research"],
  "summary": "Consent for appendectomy...",
  "entities": {
    "patient_name": "John Smith",
    "patient_email": "john.smith@example.com",
    "doctor_name": "Dr. Sarah Johnson",
    "procedure": "Appendectomy",
    "date": "2024-11-03"
  },
  "search_terms": ["john smith", "john.smith@example.com", ...],
  "processed_timestamp": "2024-11-03T00:00:00Z"
}
```

## 🚀 Getting Started

### Prerequisites
- Google Cloud Project with billing enabled
- Python 3.11+
- gcloud CLI installed and authenticated
- Git (for cloning this repository)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/consent-management-system.git
   cd consent-management-system
   ```

2. **Set up environment variables**:
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit .env with your values
   # GCP_PROJECT_ID=your-project-id
   # GCP_LOCATION=us-central1
   # API_URL=https://your-query-service-url.run.app
   ```

3. **Install dependencies**:
   ```bash
   # Install ingestion function dependencies
   cd ingestion-function
   pip install -r requirements.txt
   cd ..
   
   # Install query service dependencies
   cd query-service
   pip install -r requirements.txt
   cd ..
   ```

4. **Configure frontend**:
   - Edit `frontend/index.html` line 696
   - Replace `'https://your-query-service-url.run.app'` with your deployed API URL

## 🚀 Deployment

### Prerequisites
- Google Cloud Project with billing enabled
- gcloud CLI installed and authenticated
- Required APIs enabled (see below)

### Step 1: Set Project and Enable APIs
```bash
# Set your GCP project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable vision.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable eventarc.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 2: Create Storage Bucket
```bash
# Replace with your bucket name
gsutil mb -l us-central1 gs://YOUR_BUCKET_NAME
```

### Step 3: Deploy Ingestion Function
```bash
cd ingestion-function

# Set environment variables
gcloud functions deploy process_consent_pdf \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_consent_pdf \
  --trigger-bucket=YOUR_BUCKET_NAME \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_LOCATION=us-central1 \
  --memory=1GB \
  --timeout=540s \
  --max-instances=10
```

### Step 4: Deploy Query Service
```bash
cd ../query-service

# Deploy with environment variables
gcloud run deploy consent-query-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_LOCATION=us-central1 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --max-instances=10 \
  --port=8080
```

**Note the service URL** - you'll need it for the frontend. It will be displayed after deployment.

### Step 5: Update Frontend Configuration
Edit `frontend/index.html` line 732:
```javascript
const API_URL = 'https://YOUR-QUERY-SERVICE-URL.us-central1.run.app';
```

### Step 6: Deploy Frontend
```bash
cd ../frontend
gcloud run deploy consent-patient-portal \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --max-instances=5 \
  --port=8080
```

## 📝 Usage

### For Administrators

**Upload Consent Forms**:
```bash
gcloud storage cp patient_consent.pdf gs://consent-management-summarizer-bucket/
```

The system automatically:
- Extracts text using Vision API
- Analyzes with Gemini 2.0 Flash
- Creates patient account
- Stores data in Firestore

**Patient Credentials**:
- Email: From consent form
- Password: `{firstname}123!` (e.g., `john123!` for John Smith)

### For Patients

1. Visit the patient portal
2. Log in with email from consent form and password `{firstname}123!`
3. Ask questions in natural language:
   - "What procedures did I consent to?"
   - "Did I decline anything?"
   - "What did I agree to?"
   - "Tell me about my consent form"

## 🔐 Security Features

- **Password Hashing**: SHA-256
- **Session Management**: Token-based, 8-hour expiration
- **Data Isolation**: Firestore queries filtered by patient_email
- **Patient-Specific Access**: AI only sees patient's own documents
- **No Cross-Patient Queries**: System prevents access to other patients' data

## 🎨 Technologies Used

- **Backend**: Python 3.11, Flask
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Cloud Platform**: Google Cloud Platform
- **Database**: Firestore (NoSQL)
- **Storage**: Cloud Storage
- **AI Models**:
  - Google Cloud Vision API (OCR)
  - Google Gemini 2.0 Flash Experimental (Analysis & Queries)
- **Deployment**: Cloud Functions Gen 2, Cloud Run

## 📈 Performance

- **OCR Processing**: ~30-60 seconds per PDF (depending on pages)
- **AI Analysis**: ~5-10 seconds per document
- **Query Response**: ~2-5 seconds (including AI generation)
- **Scalability**: Auto-scales based on demand

## 🐛 Troubleshooting

**Patient can't log in**:
- Verify patient account exists in Firestore `patients` collection
- Check password hash matches (use `{firstname}123!` format)
- Ensure email matches exactly (case-insensitive)

**No consent forms found**:
- Check `entity_index` collection has document with matching `patient_email`
- Verify patient email in consent form matches patient account email

**PDF not processing**:
- Check Cloud Function logs: `gcloud functions logs read process_consent_pdf --region=us-central1 --gen2`
- Verify Vision API quota
- Check Gemini API quota

## 📚 Key Files

- `ingestion-function/main.py`: PDF processing and account creation
- `query-service/app.py`: API endpoints and query processing
- `frontend/index.html`: Patient portal UI
- `README.md`: This file

## 📞 Support

For issues:
1. Check Cloud Function logs
2. Check Cloud Run logs
3. Review Firestore data structure
4. Verify API endpoints are accessible

## 📦 Repository Structure

```
consent-management-system/
├── ingestion-function/
│   ├── main.py              # PDF processing function
│   └── requirements.txt     # Python dependencies
├── query-service/
│   ├── app.py               # Flask API service
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile          # Container configuration
├── frontend/
│   ├── index.html          # Patient portal UI
│   ├── server.py           # Simple Flask server
│   ├── requirements.txt    # Python dependencies
│   ├── Dockerfile         # Container configuration
│   └── ascension.png      # Logo image
├── .gitignore             # Git ignore rules
├── .env.example          # Environment variables template
├── config.example.py     # Configuration template
└── README.md            # This file
```

## 🔧 Configuration

### Environment Variables

Set these environment variables before deployment:

- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCP_LOCATION`: GCP region (default: `us-central1`)
- `API_URL`: Deployed Query Service API URL (for frontend)

### Frontend Configuration

Edit `frontend/index.html` line 696 to set your Query Service API URL:
```javascript
const API_URL = 'https://your-query-service-url.run.app';
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Google Cloud Platform
- Google Cloud Vision API
- Google Gemini 2.0 Flash
- Firestore

---

**Version**: 2.0  
**Last Updated**: November 2025 
**Project**: Patient Consent Management System
