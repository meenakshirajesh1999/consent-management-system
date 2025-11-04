"""
Example configuration file for the Consent Management System
Copy this file to config.py and update with your values
"""

# Google Cloud Configuration
GCP_PROJECT_ID = "your-project-id"
GCP_LOCATION = "us-central1"

# Storage Configuration
STORAGE_BUCKET_NAME = "consent-management-summarizer-bucket"

# Firestore Configuration
FIRESTORE_DATABASE = "consent-management-db"

# Query Service API URL (deployed Cloud Run URL)
QUERY_SERVICE_URL = "https://your-query-service-url.run.app"

# Frontend Configuration
FRONTEND_URL = "https://your-patient-portal-url.run.app"

