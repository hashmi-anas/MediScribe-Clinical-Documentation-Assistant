import os
import json
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def load_backend_env():
    """Load .env file directly into os.environ if present."""
    base_dir = getattr(settings, 'BASE_DIR', None)
    if base_dir:
        env_path = os.path.join(base_dir, '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
            except Exception as e:
                logger.warning(f"Failed loading .env: {e}")

load_backend_env()

class GroqService:
    """
    Server-side Groq AI Engine for MediScribe.
    Configured with required primary model `openai/gpt-oss-120b` and robust fallbacks.
    Handles LLM text generation, structured JSON extraction, and Whisper audio transcription.
    """
    def __init__(self):
        # Support env keys securely
        self.api_key = os.environ.get('GROQ_API_KEY') or os.environ.get('groq_api') or os.environ.get('GROQ_KEY')
        self.base_url = "https://api.groq.com/openai/v1"
        self.default_model = os.environ.get('GROQ_MODEL') or "openai/gpt-oss-120b"
        self.fallback_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    def is_configured(self):
        return bool(self.api_key and self.api_key.startswith('gsk_'))

    def get_model_info(self):
        return {
            "configured": self.is_configured(),
            "primary_model": self.default_model,
            "provider": "Groq LPU Inference Engine",
            "fallbacks": self.fallback_models
        }

    def chat_completion(self, messages, model=None, temperature=0.2, max_tokens=1500, response_format=None):
        """
        Calls Groq chat completion API with robust error handling and model fallback chain.
        """
        if not self.is_configured():
            logger.info("Groq API key not configured or invalid.")
            return None

        models_to_try = [model or self.default_model]
        for fb in self.fallback_models:
            if fb not in models_to_try:
                models_to_try.append(fb)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for candidate_model in models_to_try:
            payload = {
                "model": candidate_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if response_format:
                payload["response_format"] = response_format

            try:
                url = f"{self.base_url}/chat/completions"
                response = requests.post(url, headers=headers, json=payload, timeout=25)
                if response.status_code == 200:
                    data = response.json()
                    return data['choices'][0]['message']['content']
                else:
                    logger.warning(f"Groq API error with model {candidate_model} (status {response.status_code})")
            except Exception as e:
                logger.error(f"Groq API call exception for {candidate_model}: {e}")

        return None

    def transcribe_audio(self, audio_file_path):
        """
        Transcribes audio using Groq Whisper (whisper-large-v3).
        """
        if not self.is_configured() or not audio_file_path or not os.path.exists(audio_file_path):
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        url = f"{self.base_url}/audio/transcriptions"
        try:
            with open(audio_file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(audio_file_path), f, 'audio/wav')
                }
                data = {
                    'model': 'whisper-large-v3',
                    'temperature': '0.0',
                    'response_format': 'json',
                    'language': 'en'
                }
                response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
                if response.status_code == 200:
                    return response.json().get('text')
        except Exception as e:
            logger.error(f"Groq Whisper transcription exception: {e}")
        return None

    def extract_clinical_entities(self, transcript, patient_context=""):
        """
        Uses Groq LLM to extract structured clinical information in strict JSON format.
        Identifies: Symptoms, Diagnoses, Medications (with dose, frequency, duration),
        Procedures, Diagnostic tests, Allergies, Treatment Plan, Follow-Up.
        """
        system_prompt = (
            "You are a medical NLP entity extraction system for MediScribe. "
            "Analyze the doctor-patient conversation transcript and extract clinical entities. "
            "You must return ONLY a valid JSON object with the following keys:\n"
            "{\n"
            '  "symptoms": ["list of reported symptoms"],\n'
            '  "diagnoses": [{"name": "diagnosis name", "icd10": "ICD-10 code if identifiable"}],\n'
            '  "medications": [{"name": "drug", "dosage": "dose", "frequency": "sig", "duration": "time"}],\n'
            '  "procedures": ["clinical exams or procedures performed/ordered"],\n'
            '  "tests": ["diagnostic lab or imaging tests ordered"],\n'
            '  "allergies": ["identified drug or food allergies"],\n'
            '  "treatment_plan": ["key therapeutic actions"],\n'
            '  "follow_up": "recommended follow-up timeline and instructions"\n'
            "}\n"
            "Do NOT fabricate medical facts. If information was not mentioned in the transcript, use an empty list or null."
        )

        user_prompt = f"Patient Context: {patient_context}\n\nConsultation Transcript:\n{transcript}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        result = self.chat_completion(messages, response_format={"type": "json_object"}, temperature=0.1)
        if result:
            try:
                return json.loads(result)
            except Exception:
                pass
        return None

    def generate_single_document(self, doc_type, transcript, patient_info, doctor_name="Doctor", department="General Practice"):
        """
        Generates a specific clinical document on demand.
        """
        doc_instructions = {
            'SOAP': "Generate a formal SOAP Note with ### SUBJECTIVE, ### OBJECTIVE, ### ASSESSMENT, ### PLAN.",
            'CLINICAL_NOTE': "Generate a detailed Clinical Note with ### Chief Complaints, ### History of Present Illness, ### Physical Examination, ### Diagnosis, ### Treatment Plan.",
            'PRESCRIPTION': "Generate a structured Prescription Draft listing ### Prescriptions with medication name, dosage, frequency, duration, instructions, and refills.",
            'DISCHARGE_SUMMARY': "Generate a formal Discharge Summary with ### Admission Reason, ### Key Findings, ### Discharge Diagnosis, ### Discharge Medications, ### Home Care Instructions.",
            'FOLLOW_UP': "Generate a patient-friendly Follow-up Plan with ### Recommended Actions, ### Scheduled Follow-up Timeline, ### Warning Symptoms to Seek Immediate Care.",
            'REPORT': "Generate a formal Clinical Consultation Report with complete patient findings, diagnostic summaries, and physician recommendations."
        }

        instruction = doc_instructions.get(doc_type, f"Generate clinical documentation for {doc_type}.")
        system_prompt = (
            "You are MediScribe's Generative AI Clinical Documentation Assistant. "
            "Convert doctor-patient consultation transcripts into comprehensive, structured medical documentation. "
            "Never invent false medical data. Append footnote: 'AI Generated Draft — Doctor Review and Approval Required'."
        )
        user_msg = (
            f"Instruction: {instruction}\n\n"
            f"Doctor: {doctor_name} ({department})\n"
            f"Patient: {patient_info.get('name', 'Patient')}, Age {patient_info.get('age', 'N/A')}, Gender {patient_info.get('gender', 'N/A')}\n"
            f"Transcript:\n{transcript}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        return self.chat_completion(messages, temperature=0.2, max_tokens=1200)

    def generate_clinical_documents(self, transcript, patient_info, doctor_name="Doctor", department="General"):
        """
        Uses Groq to generate a complete suite of draft clinical documentation:
        1. SOAP Note
        2. Detailed Clinical Note
        3. Prescription Draft
        4. Discharge Summary
        5. Visit & Follow-up Summary
        """
        system_prompt = (
            "You are MediScribe's Generative AI Clinical Documentation Assistant. "
            "Convert doctor-patient consultation transcripts into comprehensive, highly structured medical documentation. "
            "Always include explicit header markers (### SUBJECTIVE, ### OBJECTIVE, ### ASSESSMENT, ### PLAN for SOAP; "
            "### Clinical Findings, ### Diagnosis, ### Plan for Clinical Note; "
            "### Prescriptions: with 1. Drug, Dispense, Sig, Refills for Rx; "
            "### Discharge Summary for Discharge; "
            "### Visit Summary & Follow-up for Follow-up). "
            "Always append the footnote: 'AI Generated Draft — Doctor Review and Approval Required'."
        )

        docs = {}
        types = [
            ('SOAP', f"Generate a comprehensive clinical SOAP note for patient {patient_info.get('name', 'Patient')} ({department})."),
            ('CLINICAL_NOTE', f"Generate a detailed formal Clinical Note documenting chief complaints, physical exam findings, and clinical impression for patient {patient_info.get('name', 'Patient')}."),
            ('PRESCRIPTION', f"Generate a structured Prescription Draft with exact medications, dosages, frequency, duration, and refills mentioned in the consultation."),
            ('DISCHARGE_SUMMARY', f"Generate a patient Discharge Summary with admission/visit reason, clinical findings, discharge medications, and post-discharge home care instructions."),
            ('VISIT_SUMMARY', f"Generate a clear, patient-friendly Visit Summary and Follow-up Plan detailing next steps and scheduled appointments.")
        ]

        for doc_type, instruction in types:
            user_msg = (
                f"{instruction}\n\n"
                f"Doctor: {doctor_name}\n"
                f"Patient Profile: Age {patient_info.get('age', 'N/A')}, Gender {patient_info.get('gender', 'N/A')}, Chronic: {patient_info.get('chronic', 'None')}, Allergies: {patient_info.get('allergies', 'None')}\n\n"
                f"Consultation Transcript:\n{transcript}"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
            content = self.chat_completion(messages, temperature=0.2, max_tokens=1200)
            if content:
                docs[doc_type] = content

        return docs
