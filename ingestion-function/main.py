import json
import re
import os
import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import vision
from google.cloud import firestore
from google.cloud import storage
import requests
import hashlib
import secrets
from datetime import datetime

# --- CONFIGURATION ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

# --- INITIALIZE CLIENTS ---
vertexai.init(project=PROJECT_ID, location=LOCATION)
vision_client = vision.ImageAnnotatorClient()
firestore_client = firestore.Client(database="consent-management-db")
storage_client = storage.Client()
model = GenerativeModel("gemini-2.0-flash-exp") # Using Gemini 2.0 Flash for better OCR extraction

@functions_framework.cloud_event
def process_consent_pdf(cloud_event):
    """This function is triggered by a file upload to GCS."""
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_name = data["name"]

    # --- NEW: Add a check to only process PDF files ---
    if not file_name.lower().endswith('.pdf'):
        print(f"Ignoring file '{file_name}' because it is not a PDF.")
        return

    print(f"Processing file: {file_name} from bucket: {bucket_name}")

    # 1. Run OCR on the PDF file in Cloud Storage using the Vision AI API
    gcs_source_uri = f"gs://{bucket_name}/{file_name}"
    gcs_destination_uri = f"gs://{bucket_name}/{file_name}-ocr-output/"

    mime_type = "application/pdf"
    batch_size = 2
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    gcs_source = vision.GcsSource(uri=gcs_source_uri)
    input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

    gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
    output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=batch_size)

    async_request = vision.AsyncAnnotateFileRequest(
        features=[feature], input_config=input_config, output_config=output_config
    )

    operation = vision_client.async_batch_annotate_files(requests=[async_request])
    print("Waiting for the Vision AI OCR operation to complete...")
    operation.result(timeout=420)
    print("OCR operation finished.")

    # 2. Read the OCR output text from the JSON files created by Vision AI
    storage_bucket = storage_client.get_bucket(bucket_name)
    blob_list = [
        b for b in storage_bucket.list_blobs(prefix=f"{file_name}-ocr-output/")
        if ".json" in b.name
    ]
    
    full_text = ""
    for blob in blob_list:
        json_string = blob.download_as_string()
        response = json.loads(json_string)
        for page_response in response["responses"]:
            full_text += page_response["fullTextAnnotation"]["text"]
    
    print("Successfully extracted text from OCR output.")

    # 3. Analyze the extracted text with the Gemini AI model
    prompt = f"""
    Analyze the following medical consent form text and respond ONLY with a valid JSON object.
    The JSON object should have these exact keys: "summary", "entities", "consented_items", "declined_items", "patient_id".
    
    - "summary": A brief, one-paragraph summary of the document's purpose.
    - "entities": An object containing key entities like "patient_name", "patient_email", "date_of_birth", "doctor_name", "procedure", and "date". If a value is not found, use "N/A".
    - "consented_items": A list of strings, where each string is a specific item the patient consented to.
    - "declined_items": A list of strings, where each string is a specific item the patient declined.
    - "patient_id": Extract or generate a unique identifier for the patient (e.g., email, patient number, or combination of name and DOB). This is critical for patient-specific access.
    
    IMPORTANT: Extract patient identification information carefully as it will be used for authentication and authorization.
    
    TEXT:
    {full_text}
    """
    
    try:
        response = model.generate_content(prompt)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        print("Gemini analysis complete.")
    except Exception as e:
        print(f"Error with Gemini model: {str(e)}")
        # Fallback: create a basic analysis
        cleaned_response = json.dumps({
            "summary": "Consent form processed - AI analysis failed",
            "entities": {
                "patient_name": "N/A",
                "patient_email": "N/A",
                "date_of_birth": "N/A",
                "doctor_name": "N/A", 
                "procedure": "N/A",
                "date": "N/A"
            },
            "consented_items": ["Analysis pending"],
            "declined_items": [],
            "patient_id": "unknown"
        })
        print("Using fallback analysis due to model error.")

    # 4. Save the analysis to your Firestore database
    try:
        doc_id = file_name.replace(".pdf", "")
        doc_ref = firestore_client.collection("consents").document(doc_id)
        doc_ref.set({
            "filename": file_name,
            "ai_analysis_json": cleaned_response,
            "full_text": full_text,
            "processed_timestamp": firestore.SERVER_TIMESTAMP
        })
        print(f"Successfully saved analysis for '{doc_id}' to Firestore.")
    except Exception as e:
        print(f"Error saving to Firestore: {str(e)}")
        raise e

    # 5. Store enhanced data in Firestore for query system
    try:
        _store_enhanced_analysis(doc_id, cleaned_response, full_text)
        print(f"Successfully stored enhanced analysis for '{doc_id}' in Firestore.")
    except Exception as e:
        print(f"Error storing enhanced analysis: {str(e)}")
        # Don't fail the whole process if enhanced storage fails

    # 6. Create or update patient account automatically
    try:
        analysis = json.loads(cleaned_response)
        entities = analysis.get("entities", {})
        patient_email = entities.get("patient_email", "").lower()
        patient_name = entities.get("patient_name", "N/A")
        
        if patient_email and patient_email != "n/a":
            _create_patient_account(patient_email, patient_name)
            print(f"Patient account created/updated for {patient_email}")
        else:
            print("No patient email found in consent form - skipping account creation")
    except Exception as e:
        print(f"Error creating patient account: {str(e)}")
        # Don't fail the whole process if account creation fails

    # 7. Clean up the OCR output files from the bucket
    for blob in blob_list:
        blob.delete()
    print("Cleaned up temporary OCR output files.")


def _store_enhanced_analysis(document_id: str, analysis_json: str, full_text: str) -> None:
    """Store enhanced analysis in Firestore for better querying with patient isolation"""
    try:
        analysis = json.loads(analysis_json)
        entities = analysis.get("entities", {})
        
        # Create searchable entity data
        entity_data = {}
        search_terms = []
        
        for entity_type, entity_value in entities.items():
            if entity_value and entity_value != "N/A":
                entity_data[entity_type] = entity_value
                # Create searchable terms for better querying
                search_terms.append(f"{entity_type}:{entity_value}")
                search_terms.append(entity_value.lower())
        
        # Extract patient identifier for secure access control
        patient_id = analysis.get("patient_id", "unknown")
        patient_email = entities.get("patient_email", "N/A")
        
        # Store in a separate collection for entity-based queries
        entity_doc_ref = firestore_client.collection("entity_index").document(document_id)
        entity_doc_ref.set({
            "document_id": document_id,
            "entities": entity_data,
            "search_terms": search_terms,
            "patient_name": entities.get("patient_name", "N/A"),
            "patient_id": patient_id,
            "patient_email": patient_email.lower() if patient_email != "N/A" else "N/A",
            "consented_items": analysis.get("consented_items", []),
            "declined_items": analysis.get("declined_items", []),
            "summary": analysis.get("summary", ""),
            "processed_timestamp": firestore.SERVER_TIMESTAMP
        })
        
        print(f"Enhanced entity data stored for {document_id} (patient: {patient_id})")
        
    except Exception as e:
        print(f"Enhanced storage error: {e}")


def _create_patient_account(patient_email: str, patient_name: str) -> None:
    """Create or update patient account automatically from consent form"""
    try:
        # Generate default password based on patient info (first 6 chars of name + DOB if available)
        # Format: FirstName + "123!" (simple default - in production, send email with password)
        default_password = f"{patient_name.split()[0].lower() if patient_name != 'N/A' else 'patient'}123!"
        
        # Hash the password
        password_hash = hashlib.sha256(default_password.encode()).hexdigest()
        
        # Check if patient already exists
        patients_ref = firestore_client.collection("patients")
        existing_patients = patients_ref.where("email", "==", patient_email).limit(1).stream()
        
        existing_patient = None
        for doc in existing_patients:
            existing_patient = doc
            break
        
        if existing_patient:
            # Update existing patient (but keep password if already set by user)
            existing_data = existing_patient.to_dict()
            update_data = {
                "patient_name": patient_name,
                "email": patient_email,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            # Only update password if it hasn't been changed by user (check if it's still default format)
            if not existing_data.get("password_hash"):
                update_data["password_hash"] = password_hash
                update_data["default_password"] = default_password
            
            existing_patient.reference.update(update_data)
            print(f"Updated existing patient account for {patient_email}")
        else:
            # Create new patient account
            patient_id = secrets.token_urlsafe(16)
            patients_ref.document(patient_id).set({
                "email": patient_email,
                "password_hash": password_hash,
                "patient_name": patient_name,
                "default_password": default_password,  # Store for reference (remove in production)
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"Created new patient account for {patient_email} with password: {default_password}")
            
    except Exception as e:
        print(f"Error creating patient account: {e}")
        raise e