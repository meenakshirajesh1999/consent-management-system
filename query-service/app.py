import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel
import logging
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

# Initialize clients (lazy loading to save memory)
firestore_client = None
storage_client = None
model = None

def get_firestore_client():
    global firestore_client
    if firestore_client is None:
        firestore_client = firestore.Client(database="consent-management-db")
    return firestore_client

def get_storage_client():
    global storage_client
    if storage_client is None:
        storage_client = storage.Client()
    return storage_client

def get_model():
    global model
    if model is None:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel("gemini-2.0-flash-exp")  # Better model for OCR understanding
    return model

# Session store (in production, use Redis or similar)
active_sessions = {}

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_session(f):
    """Decorator to verify patient session"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.headers.get('Authorization')
        if not session_token or session_token not in active_sessions:
            return jsonify({"error": "Unauthorized. Please log in."}), 401
        
        session_data = active_sessions[session_token]
        if datetime.now() > session_data['expires']:
            del active_sessions[session_token]
            return jsonify({"error": "Session expired. Please log in again."}), 401
        
        # Add patient email to request context
        request.patient_email = session_data['email']
        return f(*args, **kwargs)
    return decorated_function


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
logging.basicConfig(level=logging.INFO)

@app.route('/register', methods=['POST'])
def register_patient():
    """Register a new patient"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        patient_name = data.get('patient_name', '').strip()
        date_of_birth = data.get('date_of_birth', '').strip()
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        # Check if patient already exists
        firestore_client = get_firestore_client()
        patients_ref = firestore_client.collection("patients")
        existing = patients_ref.where("email", "==", email).limit(1).stream()
        
        if list(existing):
            return jsonify({"error": "Patient already registered"}), 409
        
        # Create patient record
        patient_id = str(uuid.uuid4())
        patients_ref.document(patient_id).set({
            "email": email,
            "password_hash": hash_password(password),
            "patient_name": patient_name,
            "date_of_birth": date_of_birth,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        
        logging.info(f"New patient registered: {email}")
        return jsonify({
            "message": "Registration successful",
            "email": email
        })
        
    except Exception as e:
        logging.error(f"Registration error: {str(e)}")
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

@app.route('/login', methods=['POST'])
def login_patient():
    """Patient login"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        # Find patient
        firestore_client = get_firestore_client()
        patients_ref = firestore_client.collection("patients")
        patients = patients_ref.where("email", "==", email).limit(1).stream()
        
        patient_doc = None
        for doc in patients:
            patient_doc = doc.to_dict()
            break
        
        if not patient_doc:
            return jsonify({"error": "Invalid email or password"}), 401
        
        # Verify password
        if patient_doc.get('password_hash') != hash_password(password):
            return jsonify({"error": "Invalid email or password"}), 401
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        active_sessions[session_token] = {
            'email': email,
            'patient_name': patient_doc.get('patient_name', 'N/A'),
            'expires': datetime.now() + timedelta(hours=8)
        }
        
        logging.info(f"Patient logged in: {email}")
        return jsonify({
            "message": "Login successful",
            "session_token": session_token,
            "patient_name": patient_doc.get('patient_name', 'N/A'),
            "email": email
        })
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@app.route('/logout', methods=['POST'])
@verify_session
def logout_patient():
    """Patient logout"""
    session_token = request.headers.get('Authorization')
    if session_token in active_sessions:
        del active_sessions[session_token]
    return jsonify({"message": "Logged out successfully"})

@app.route('/query', methods=['POST'])
@verify_session
def handle_query():
    """Handle user queries about consent forms - patient-specific only"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        patient_email = request.patient_email  # From session verification
        
        if not query:
            return jsonify({"error": "No query provided"}), 400
        
        logging.info(f"Processing query for patient {patient_email}: {query}")
        
        # Search for patient's consent documents ONLY
        relevant_docs = search_patient_documents(patient_email)
        
        if not relevant_docs:
            return jsonify({
                "query": query,
                "answer": "I don't have any consent forms on file for you. Please contact your healthcare provider.",
                "sources": []
            })
        
        logging.info(f"Found {len(relevant_docs)} documents for patient")
        
        # Generate answer using AI - restricted to patient's own documents
        answer = generate_answer(query, relevant_docs)
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": [doc['filename'] for doc in relevant_docs]
        })
        
    except Exception as e:
        logging.error(f"Error processing query: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

def extract_entities(query):
    """Extract key entities from the user query"""
    # Simple entity extraction - look for patient IDs, names, etc.
    entities = []
    
    # Look for patient IDs (e.g., "patient 45B", "45B")
    import re
    patient_pattern = r'patient\s+(\w+)|\b(\w+)\b'
    matches = re.findall(patient_pattern, query.lower())
    for match in matches:
        entity = match[0] or match[1]
        if entity and len(entity) > 1:
            entities.append(entity)
    
    # Look for keywords
    keywords = ['consent', 'decline', 'agree', 'procedure', 'research']
    for keyword in keywords:
        if keyword in query.lower():
            entities.append(keyword)
    
    return entities

def search_patient_documents(patient_email):
    """Search Firestore for documents belonging to specific patient only"""
    docs = []
    
    try:
        firestore_client = get_firestore_client()
        
        # Query entity_index for patient-specific documents
        entity_collection = firestore_client.collection("entity_index")
        patient_docs = entity_collection.where("patient_email", "==", patient_email).stream()
        
        for doc in patient_docs:
            doc_data = doc.to_dict()
            docs.append({
                'id': doc.id,
                'filename': doc_data.get('document_id', 'unknown'),
                'summary': doc_data.get('summary', ''),
                'consented_items': doc_data.get('consented_items', []),
                'declined_items': doc_data.get('declined_items', []),
                'patient_name': doc_data.get('patient_name', 'N/A'),
                'entities': doc_data.get('entities', {})
            })
        
        logging.info(f"Found {len(docs)} documents for patient {patient_email}")
        
    except Exception as e:
        logging.error(f"Error searching patient documents: {str(e)}")
    
    return docs

def generate_answer(query, relevant_docs):
    """Generate an answer using AI based on relevant documents - patient-specific"""
    if not relevant_docs:
        return "No relevant consent forms found for your query."
    
    # Prepare context from relevant documents (patient's own documents only)
    context = ""
    for doc in relevant_docs[:3]:  # Limit to first 3 docs to save tokens
        context += f"\nConsent Form: {doc['filename']}\n"
        context += f"Patient: {doc.get('patient_name', 'N/A')}\n"
        context += f"Summary: {doc.get('summary', 'N/A')}\n"
        context += f"Items Consented To: {', '.join(doc.get('consented_items', [])) if doc.get('consented_items') else 'None listed'}\n"
        context += f"Items Declined: {', '.join(doc.get('declined_items', [])) if doc.get('declined_items') else 'None listed'}\n"
    
    prompt = f"""
    You are a helpful medical consent assistant. Based ONLY on the patient's consent form information below, 
    answer their question clearly and concisely in a friendly, professional tone.
    
    IMPORTANT SECURITY RULES:
    - Only discuss information from the patient's OWN consent forms provided below
    - Never mention or reference other patients
    - If asked about other patients, politely decline
    - Keep responses focused on the patient's own medical consents
    
    Patient's Question: {query}
    
    Patient's Consent Form Information:
    {context}
    
    Provide a direct, helpful answer based ONLY on the information above. If the information is not available 
    in the provided documents, say so clearly and suggest they contact their healthcare provider.
    """
    
    try:
        model = get_model()
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Error generating AI answer: {str(e)}")
        # Fallback: simple response
        return generate_fallback_answer(query, relevant_docs)

def generate_fallback_answer(query, relevant_docs):
    """Fallback answer generation without AI"""
    query_lower = query.lower()
    
    for doc in relevant_docs:
        if 'decline' in query_lower:
            declined = doc.get('declined_items', [])
            if declined:
                return f"Based on your consent form, you declined: {', '.join(declined)}"
            else:
                return "Based on your consent form, you didn't decline any items."
        
        if 'consent' in query_lower or 'agree' in query_lower:
            consented = doc.get('consented_items', [])
            if consented:
                return f"Based on your consent form, you consented to: {', '.join(consented)}"
            else:
                return "Based on your consent form, no specific consent items were listed."
    
    return f"I found your consent form but couldn't extract specific information. Please contact your healthcare provider for details."

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads to Cloud Storage"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Only PDF files are allowed"}), 400
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Upload to Cloud Storage
        storage_client = get_storage_client()
        bucket_name = "consent-management-summarizer-bucket"
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(unique_filename)
        
        # Upload file
        blob.upload_from_file(file)
        
        logging.info(f"File uploaded successfully: {unique_filename}")
        
        return jsonify({
            "message": "File uploaded successfully",
            "filename": unique_filename,
            "original_name": file.filename
        })
        
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route('/ask', methods=['POST'])
def ask_question():
    """Enhanced query endpoint using Firestore for entity resolution"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        session_id = data.get('session_id', 'default')
        
        if not question:
            return jsonify({"error": "No question provided"}), 400
        
        print(f"Processing question: {question}")
        
        # Step 1: Extract key entity from question
        key_entity = _extract_key_entity(question)
        
        # Step 2: Use Firestore to find related document
        if key_entity:
            document_data = _resolve_document_from_entity(key_entity)
        else:
            # For general questions, get the most recent document
            document_data = _get_most_recent_document()
        
        if not document_data:
            return jsonify({"error": "No consent form found"}), 404
        
        # Step 3: Generate answer
        answer = _generate_contextual_answer(question, document_data)
        
        return jsonify({
            "answer": answer,
            "document_id": document_data.get("document_id"),
            "entity": key_entity
        })
        
    except Exception as e:
        print(f"Error processing question: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

def _extract_key_entity(question):
    """Extract key entity from question"""
    import re
    # Look for patient patterns
    patient_patterns = [
        r'patient\s+(\w+)',
        r'(\w+)\s+declined',
        r'(\w+)\s+consented',
        r'what\s+did\s+(\w+)',
        r'(\w+)\s+patient'
    ]
    
    for pattern in patient_patterns:
        match = re.search(pattern, question.lower())
        if match:
            return match.group(1)
    
    return None

def _resolve_document_from_entity(entity):
    """Use Firestore to find document data for entity"""
    try:
        firestore_client = get_firestore_client()
        
        # Search in entity_index collection
        entity_collection = firestore_client.collection("entity_index")
        
        # Try exact match on patient_name
        docs = entity_collection.where("patient_name", "==", entity).stream()
        for doc in docs:
            return doc.to_dict()
        
        # Try partial match on search_terms
        docs = entity_collection.where("search_terms", "array_contains", entity.lower()).stream()
        for doc in docs:
            return doc.to_dict()
        
        # Try partial match on patient_name
        docs = entity_collection.where("patient_name", ">=", entity).where("patient_name", "<=", entity + "\uf8ff").stream()
        for doc in docs:
            return doc.to_dict()
            
    except Exception as e:
        print(f"Firestore entity resolution error: {e}")
    return None

def _get_most_recent_document():
    """Get the most recently processed document"""
    try:
        firestore_client = get_firestore_client()
        
        # Get all documents from entity_index collection and return the first one
        docs = firestore_client.collection("entity_index").limit(1).stream()
        
        for doc in docs:
            return doc.to_dict()
            
    except Exception as e:
        print(f"Error getting most recent document: {e}")
    return None

def _generate_contextual_answer(question, document_data):
    """Generate answer based on document data"""
    try:
        document_id = document_data.get("document_id", "Unknown")
        question_lower = question.lower()
        
        if 'decline' in question_lower:
            declined = document_data.get('declined_items', [])
            if declined:
                return f"Based on {document_id}, the following items were declined: {', '.join(declined)}"
            else:
                return f"Based on {document_id}, no items were declined."
        
        if 'consent' in question_lower or 'agree' in question_lower:
            consented = document_data.get('consented_items', [])
            if consented:
                return f"Based on {document_id}, the following items were consented to: {', '.join(consented)}"
            else:
                return f"Based on {document_id}, no specific consent items were found."
        
        # General summary
        summary_text = document_data.get('summary', 'No summary available.')
        return f"Based on {document_id}: {summary_text}"
        
    except Exception as e:
        print(f"Answer generation error: {e}")
        return f"Found document but couldn't generate specific answer."

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "consent-query-api"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
