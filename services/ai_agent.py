import re
import json
import logging
from django.utils import timezone
from authentication.models import PatientProfile, DoctorProfile
from consultations.models import AuditLog
from .groq_service import GroqService
from .permissions import PermissionValidator
from .action_executor import ActionExecutor

logger = logging.getLogger(__name__)

class AIAgent:
    """
    Action-Execution AI Agent for MediScribe.
    
    Pipeline:
    User Message -> Role Identification -> Hybrid Intent Detection (Keywords + Rules + Groq LLM)
    -> Entity Extraction -> Permission Validation -> Backend Action Execution -> LLM Response Formatting -> Audit Log
    """
    def __init__(self):
        self.groq = GroqService()

    def process_request(self, user, query, conversation_history=None, current_context=None, confirmed_action=None):
        """
        Main entry point for all 3 role-specific AI chatbots (Doctor, Patient, Admin).
        """
        conversation_history = conversation_history or []
        current_context = current_context or {}
        role = PermissionValidator.get_user_role(user)

        # 1. Handle explicit confirmation from UI
        if confirmed_action:
            action_name = confirmed_action.get('action_name')
            entities = confirmed_action.get('entities', {})
            execution_res = ActionExecutor.execute(action_name, user, entities=entities, context=current_context, confirmed=True)
            self._log_ai_action(user, role, f"Confirmed: {action_name}", action_name, execution_res.get('status'))
            return execution_res

        clean_query = (query or "").strip()
        if not clean_query:
            return {
                'status': 'error',
                'success': False,
                'message': "Please enter a message or command."
            }

        # 2. Extract Entities from Query and Context
        entities = self._extract_entities(clean_query, current_context)

        # 3. Hybrid Intent Detection
        intent_name = self._detect_intent(clean_query, role, current_context, entities)

        # 4. Action Execution
        execution_res = ActionExecutor.execute(intent_name, user, entities=entities, context=current_context)

        # 5. Context Persistence (e.g. remember patient_id, consultation_id)
        if entities.get('patient_id'):
            current_context['patient_id'] = entities['patient_id']
        if execution_res.get('data') and isinstance(execution_res['data'], dict):
            if execution_res['data'].get('consultation_id'):
                current_context['consultation_id'] = execution_res['data']['consultation_id']
            if execution_res['data'].get('patient_id'):
                current_context['patient_id'] = execution_res['data']['patient_id']

        # 6. Audit Logging
        self._log_ai_action(user, role, clean_query, intent_name, execution_res.get('status'))

        return execution_res

    def _extract_entities(self, query, context):
        """
        Extracts entities such as patient_id, email, username, and search queries.
        """
        entities = {}
        q = query.lower()

        # Patient ID extraction (e.g., "patient 102", "patient #1001", "pt-1002")
        pat_match = re.search(r'patient\s*(?:id|#|\:)?\s*(\d+)', q, re.IGNORECASE)
        if pat_match:
            entities['patient_id'] = int(pat_match.group(1))
        elif 'patient_id' in context:
            entities['patient_id'] = context['patient_id']

        # Email extraction
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
        if email_match:
            entities['email'] = email_match.group(0)

        # User / ID extraction (e.g., "user 105", "disable user 105")
        user_match = re.search(r'user\s*(\w+)', q, re.IGNORECASE)
        if user_match:
            entities['username'] = user_match.group(1)

        # General search query
        entities['query'] = query
        return entities

    def _detect_intent(self, query, role, context, entities):
        """
        Deterministic Keyword & Rule Mapping + LLM Semantic Understanding.
        """
        q = (query or "").lower().strip()

        # --- Greetings & Casual Conversational Starters ---
        if q in ['hi', 'hii', 'hiii', 'hello', 'hey', 'heyy', 'hola', 'greetings', 'good morning', 'good afternoon', 'good evening'] or q.startswith('hi ') or q.startswith('hello ') or q.startswith('hey '):
            return 'GREETING'

        # --- Module / Keyword Specific Info Questions ---
        if any(k in q for k in ['what is speech recognition', 'speech recognition module', 'what is whisper', 'speech module']):
            return 'SPEECH_RECOGNITION_INFO'
        if any(k in q for k in ['what is nlp', 'nlp processing', 'natural language processing', 'nlp module', 'medical entity extraction']):
            return 'NLP_PROCESSING_INFO'
        if any(k in q for k in ['what is llm', 'llm generation', 'gpt-oss', 'what is gpt', 'generative ai module', 'ai model']):
            if role == 'ADMIN' and any(k in q for k in ['config', 'status', 'show']):
                return 'VIEW_AI_MODEL_CONFIG'
            return 'LLM_GENERATION_INFO'
        if any(k in q for k in ['what is reporting', 'reporting module', 'report generation module']):
            return 'REPORTING_INFO'
        if any(k in q for k in ['what is integration', 'ehr integration', 'fhir', 'hl7']):
            return 'INTEGRATION_INFO'
        if any(k in q for k in ['what can i do', 'help', 'commands', 'capabilities', 'what are your features', 'options']):
            return 'USER_CAPABILITIES'

        # Keyword: "speech" / "speech recognition" / "transcription" / "audio" / "voice"
        if q in ['speech', 'speech recognition', 'transcription', 'audio', 'voice']:
            return 'SPEECH_RECOGNITION_INFO'

        # Keyword: "nlp" / "symptoms" / "diagnosis" / "medications" / "medical entities"
        if q in ['nlp', 'symptoms', 'diagnosis', 'medications', 'medical entities']:
            if role == 'DOCTOR':
                return 'EXTRACT_ENTITIES'
            return 'NLP_PROCESSING_INFO'

        # Keyword: "prescription" / "medicine" / "medication"
        if q in ['prescription', 'medicine', 'medication']:
            if role == 'DOCTOR':
                return 'VIEW_PREVIOUS_PRESCRIPTIONS'
            elif role == 'PATIENT':
                return 'VIEW_OWN_PRESCRIPTIONS'

        # Keyword: "patient" / "patient records" / "medical history" / "clinical history" / "patient history"
        if q in ['patient', 'patient records', 'medical history', 'clinical history', 'patient history']:
            if role == 'PATIENT':
                return 'VIEW_OWN_MEDICAL_RECORDS'
            elif role == 'DOCTOR':
                return 'VIEW_PATIENT_HISTORY'
            else:
                return 'VIEW_PATIENTS_LIST'

        # Keyword: "audit" / "audit logs" / "audit log"
        if q in ['audit', 'audit logs', 'audit log']:
            if role == 'ADMIN':
                return 'VIEW_AUDIT_LOGS'
            return 'INTEGRATION_INFO'

        # Keyword: "system" / "system status"
        if q in ['system', 'system status']:
            if role == 'ADMIN':
                return 'VIEW_SYSTEM_STATUS'
            return 'INTEGRATION_INFO'

        # --- Role: PATIENT Intents ---
        if role == 'PATIENT':
            # Check for illegal access attempts to another patient
            if entities.get('patient_id'):
                return 'VIEW_OWN_MEDICAL_RECORDS' # ActionExecutor will enforce permission check & return isolation error

            if any(k in q for k in ['prescription', 'prescriptions', 'medicine', 'medication', 'drug', 'rx', 'dose']):
                return 'VIEW_OWN_PRESCRIPTIONS'
            if any(k in q for k in ['discharge', 'discharge summary', 'discharge note', 'discharge papers']):
                return 'VIEW_OWN_DISCHARGE_SUMMARY'
            if any(k in q for k in ['follow-up', 'follow up', 'followup', 'next visit', 'next step', 'recommendation']):
                return 'VIEW_OWN_FOLLOWUP'
            if any(k in q for k in ['consultation', 'consultations', 'visits', 'visit history', 'previous visit', 'history of visit', 'august 20']):
                return 'VIEW_OWN_CONSULTATIONS'
            if any(k in q for k in ['report', 'reports', 'clinical report', 'lab report', 'diagnostic']):
                return 'VIEW_OWN_REPORTS'
            if any(k in q for k in ['record', 'records', 'medical record', 'medical history', 'diagnosis', 'allergies', 'chronic', 'history']):
                return 'VIEW_OWN_MEDICAL_RECORDS'
            if any(k in q for k in ['profile', 'my account', 'my details', 'my info']):
                return 'VIEW_OWN_PROFILE'
            if any(k in q for k in ['explain', 'understand', 'what does this mean', 'meaning']):
                return 'EXPLAIN_DOCUMENT'
            if any(k in q for k in ['search', 'find']):
                return 'SEARCH_OWN_RECORDS'
            if any(k in q for k in ['logout', 'sign out']):
                return 'LOGOUT'
            return 'VIEW_OWN_MEDICAL_RECORDS'

        # --- Role: DOCTOR Intents ---
        if role == 'DOCTOR':
            if any(k in q for k in ['start consultation', 'new consultation', 'create consultation', 'begin consultation', 'start a new consultation', 'open consultation']):
                return 'START_CONSULTATION'
            if any(k in q for k in ['save this clinical note', 'save record', 'save documentation', 'approve document', 'verify generated', 'save this note', 'save note', 'approve']):
                return 'APPROVE_DOCUMENT'
            if any(k in q for k in ['process consultation', 'process today', 'process the consultation', 'process clinical conversation']):
                return 'PROCESS_CONSULTATION'
            if any(k in q for k in ['convert this consultation audio', 'convert audio', 'speech to text', 'transcribe', 'transcription']):
                return 'TRANSCRIBE_AUDIO'
            if any(k in q for k in ['extract symptoms', 'extract diagnosis', 'extract medication', 'extract medical entities', 'extract']):
                return 'EXTRACT_ENTITIES'
            if any(k in q for k in ['generate soap', 'generate soap note', 'generate soap notes', 'soap note', 'soap notes', 'create soap']):
                return 'GENERATE_SOAP_NOTE'
            if any(k in q for k in ['generate clinical note', 'generate clinical notes', 'clinical note', 'clinical notes', 'draft note']):
                return 'GENERATE_CLINICAL_NOTE'
            if any(k in q for k in ['generate prescription', 'prepare prescription', 'create prescription', 'make a prescription', 'prescription']):
                if 'show' in q or 'view' in q or 'previous' in q:
                    return 'VIEW_PREVIOUS_PRESCRIPTIONS'
                return 'GENERATE_PRESCRIPTION'
            if any(k in q for k in ['generate discharge', 'discharge summary', 'discharge summary generation']):
                return 'GENERATE_DISCHARGE_SUMMARY'
            if any(k in q for k in ['generate follow-up', 'follow-up recommendation', 'follow up recommendation', 'create follow-up']):
                return 'GENERATE_FOLLOWUP'
            if any(k in q for k in ['generate a report', 'generate report', 'create report', 'clinical report']):
                if 'show' in q or 'view' in q or 'previous' in q:
                    return 'VIEW_PREVIOUS_REPORTS'
                return 'GENERATE_REPORT'
            if any(k in q for k in ['show patient', 'medical history', 'patient history', 'view patient', 'patient record']):
                return 'VIEW_PATIENT_HISTORY'
            if any(k in q for k in ['search patient', 'search record', 'find patient']):
                return 'SEARCH_PATIENT_RECORDS'
            if any(k in q for k in ['recent consultation', 'previous consultation', 'my consultations', 'today\'s patient', 'consultations']):
                return 'VIEW_PREVIOUS_CONSULTATIONS'
            if any(k in q for k in ['logout', 'sign out']):
                return 'LOGOUT'
            return 'VIEW_PREVIOUS_CONSULTATIONS'

        # --- Role: ADMIN Intents ---
        if role == 'ADMIN':
            if any(k in q for k in ['disable user', 'deactivate user', 'block user']):
                return 'DISABLE_USER'
            if any(k in q for k in ['enable user', 'activate user', 'unblock user']):
                return 'ENABLE_USER'
            if any(k in q for k in ['find doctor with email', 'find doctor', 'doctor with email', 'search doctor']):
                return 'FIND_DOCTOR_BY_EMAIL'
            if any(k in q for k in ['show all users', 'show users', 'all users', 'user management', 'users']):
                return 'VIEW_ALL_USERS'
            if any(k in q for k in ['show all patients', 'show patients', 'all patients', 'patient management', 'patients']):
                return 'VIEW_PATIENTS_LIST'
            if any(k in q for k in ['inactive user', 'inactive users', 'disabled user', 'disabled users']):
                return 'VIEW_INACTIVE_USERS'
            if any(k in q for k in ['today\'s audit', 'today audit', 'recent audit activity']):
                return 'VIEW_TODAYS_AUDIT_ACTIVITY'
            if any(k in q for k in ['audit log', 'audit logs', 'audit trail', 'audit']):
                return 'VIEW_AUDIT_LOGS'
            if any(k in q for k in ['security event', 'security events', 'security activity', 'security log']):
                return 'VIEW_SECURITY_EVENTS'
            if any(k in q for k in ['ai model configuration', 'ai model', 'model status', 'model config']):
                return 'VIEW_AI_MODEL_CONFIG'
            if any(k in q for k in ['system statistic', 'system statistics', 'statistics', 'stats']):
                return 'VIEW_SYSTEM_STATS'
            if any(k in q for k in ['system status', 'health status', 'server status', 'application health']):
                return 'VIEW_SYSTEM_STATUS'
            if any(k in q for k in ['recent user registration', 'recent registration', 'new registration', 'new signups']):
                return 'VIEW_RECENT_REGISTRATIONS'
            if any(k in q for k in ['logout', 'sign out']):
                return 'LOGOUT'
            return 'VIEW_SYSTEM_STATS'

        # Universal fallback
        return 'USER_CAPABILITIES'

    def _log_ai_action(self, user, role, query, action_name, status):
        try:
            AuditLog.objects.create(
                user=user,
                action=f"AI Agent [{role}] Action: {action_name} | Status: {status} | Query: '{query[:60]}'"
            )
        except Exception as e:
            logger.warning(f"Failed to create AI audit log: {e}")
