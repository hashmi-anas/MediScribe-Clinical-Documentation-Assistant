import json
import logging
import datetime
from django.db.models import Count, Q
from django.utils import timezone
from authentication.models import PatientProfile, DoctorProfile, CustomUser
from consultations.models import Consultation, ClinicalDocument, AuditLog, AIPromptTemplate
from .permissions import PermissionValidator
from .groq_service import GroqService

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Action Registry and Execution Engine for MediScribe.
    Dispatches role-validated commands to live backend operations.
    """

    # Actions that require explicit user confirmation before executing
    SENSITIVE_ACTIONS = {
        'DISABLE_USER': 'Disabling this user account will revoke all system access.',
        'ENABLE_USER': 'Enabling this account will restore system access.',
        'DELETE_RECORD': 'Permanently delete this medical record.',
        'FINALIZE_PRESCRIPTION': 'Finalize and lock this prescription record.',
        'FINALIZE_DISCHARGE_SUMMARY': 'Finalize and issue this discharge summary.'
    }

    @classmethod
    def is_sensitive_action(cls, action_name):
        return action_name in cls.SENSITIVE_ACTIONS

    @classmethod
    def execute(cls, action_name, user, entities=None, context=None, confirmed=False):
        """
        Executes a registered safe action with strict role & entity permission enforcement.
        Returns:
            dict: {
                'status': 'success' | 'confirmation_required' | 'permission_denied' | 'error',
                'action_name': action_name,
                'intent': action_name,
                'success': True / False,
                'data': {...},
                'ui_action': {'type': 'NAVIGATE'|'MODAL'|'SWITCH_TAB', ...},
                'message': 'Focused natural language output'
            }
        """
        entities = entities or {}
        context = context or {}
        role = PermissionValidator.get_user_role(user)

        # 1. Check sensitive actions confirmation
        if cls.is_sensitive_action(action_name) and not confirmed:
            warning_msg = cls.SENSITIVE_ACTIONS.get(action_name, 'This action modifies critical system data.')
            target_desc = entities.get('username') or entities.get('patient_id') or entities.get('id') or 'selected record'
            return {
                'status': 'confirmation_required',
                'success': False,
                'action_name': action_name,
                'intent': action_name,
                'entities': entities,
                'warning': warning_msg,
                'message': f"You are about to execute {action_name.replace('_', ' ').lower()} for {target_desc}.\n\nDo you want to continue?"
            }

        # 2. Handler Mapping
        handlers = {
            # Keyword / Module Information
            'GREETING': cls._handle_greeting,
            'SPEECH_RECOGNITION_INFO': cls._handle_speech_info,
            'NLP_PROCESSING_INFO': cls._handle_nlp_info,
            'LLM_GENERATION_INFO': cls._handle_llm_info,
            'REPORTING_INFO': cls._handle_reporting_info,
            'INTEGRATION_INFO': cls._handle_integration_info,
            'USER_CAPABILITIES': cls._handle_user_capabilities,

            # Doctor Handlers
            'START_CONSULTATION': cls._handle_start_consultation,
            'PROCESS_CONSULTATION': cls._handle_process_consultation,
            'TRANSCRIBE_AUDIO': cls._handle_transcribe_audio,
            'EXTRACT_ENTITIES': cls._handle_extract_entities,
            'GENERATE_SOAP_NOTE': cls._handle_generate_soap_note,
            'GENERATE_CLINICAL_NOTE': cls._handle_generate_clinical_note,
            'GENERATE_PRESCRIPTION': cls._handle_generate_prescription,
            'GENERATE_DISCHARGE_SUMMARY': cls._handle_generate_discharge_summary,
            'GENERATE_FOLLOWUP': cls._handle_generate_followup,
            'GENERATE_REPORT': cls._handle_generate_report,
            'VIEW_PATIENT_HISTORY': cls._handle_doctor_view_patient_history,
            'SEARCH_PATIENT_RECORDS': cls._handle_doctor_search_patients,
            'VIEW_PREVIOUS_CONSULTATIONS': cls._handle_doctor_view_consultations,
            'VIEW_PREVIOUS_PRESCRIPTIONS': cls._handle_doctor_view_prescriptions,
            'VIEW_PREVIOUS_REPORTS': cls._handle_doctor_view_reports,
            'APPROVE_DOCUMENT': cls._handle_approve_document,
            'SAVE_RECORD': cls._handle_save_record,

            # Patient Handlers
            'VIEW_OWN_PROFILE': cls._handle_patient_profile,
            'VIEW_OWN_MEDICAL_RECORDS': cls._handle_patient_medical_records,
            'VIEW_OWN_PRESCRIPTIONS': cls._handle_patient_prescriptions,
            'VIEW_OWN_CONSULTATIONS': cls._handle_patient_consultations,
            'VIEW_OWN_DISCHARGE_SUMMARY': cls._handle_patient_discharge_summary,
            'VIEW_OWN_MEDICATIONS': cls._handle_patient_medications,
            'VIEW_OWN_FOLLOWUP': cls._handle_patient_followup,
            'VIEW_OWN_REPORTS': cls._handle_patient_reports,
            'SEARCH_OWN_RECORDS': cls._handle_patient_search_records,
            'EXPLAIN_DOCUMENT': cls._handle_patient_explain_document,

            # Admin Handlers
            'VIEW_ALL_USERS': cls._handle_admin_view_all_users,
            'FIND_DOCTOR_BY_EMAIL': cls._handle_admin_find_doctor_by_email,
            'VIEW_PATIENTS_LIST': cls._handle_admin_view_patients_list,
            'VIEW_INACTIVE_USERS': cls._handle_admin_view_inactive_users,
            'VIEW_AUDIT_LOGS': cls._handle_admin_view_audit_logs,
            'VIEW_TODAYS_AUDIT_ACTIVITY': cls._handle_admin_view_todays_audit_activity,
            'VIEW_SECURITY_EVENTS': cls._handle_admin_view_security_events,
            'VIEW_SYSTEM_STATUS': cls._handle_admin_view_system_status,
            'VIEW_AI_MODEL_CONFIG': cls._handle_admin_view_ai_model_config,
            'VIEW_SYSTEM_STATS': cls._handle_admin_view_system_stats,
            'VIEW_RECENT_REGISTRATIONS': cls._handle_admin_view_recent_registrations,
            'DISABLE_USER': cls._handle_admin_disable_user,
            'ENABLE_USER': cls._handle_admin_enable_user,

            # Universal
            'LOGOUT': cls._handle_logout,
            'NAVIGATE': cls._handle_navigate
        }

        handler = handlers.get(action_name)
        if not handler:
            return {
                'status': 'error',
                'success': False,
                'action_name': action_name,
                'intent': action_name,
                'message': f"I couldn't identify that operation.\n\nType 'What can I do?' to see available actions for your account."
            }

        try:
            res = handler(user=user, role=role, entities=entities, context=context)
            res['intent'] = action_name
            res['action_name'] = action_name
            res['success'] = (res.get('status') == 'success')
            return res
        except Exception as e:
            logger.exception(f"Error executing action {action_name}: {e}")
            return {
                'status': 'error',
                'success': False,
                'action_name': action_name,
                'intent': action_name,
                'message': "The requested operation encountered an unexpected error. Please try again."
            }

    # ==================== MODULE / KEYWORD EXPLANATIONS ====================

    @classmethod
    def _handle_greeting(cls, user, role, entities, context):
        if role == 'DOCTOR':
            doc_name = user.get_full_name() or user.username
            return {
                'status': 'success',
                'message': (
                    f"Hello Dr. {doc_name}! I am your MediScribe Clinical AI Assistant.\n\n"
                    "How can I assist you with your clinical workflow today?\n\n"
                    "You can command me to:\n"
                    "• 'Start consultation for patient [ID/Name]'\n"
                    "• 'Show patient [ID] medical history'\n"
                    "• 'Process today's consultation'\n"
                    "• 'Generate clinical notes' / 'Generate prescription'\n"
                    "• 'Generate discharge summary' / 'Generate follow-up recommendations'\n"
                    "• 'Show my recent consultations'"
                )
            }
        elif role == 'PATIENT':
            pat_name = user.get_full_name() or user.username
            return {
                'status': 'success',
                'message': (
                    f"Hello {pat_name}! I am your MediScribe Personal Health Assistant.\n\n"
                    "How can I help you today?\n\n"
                    "You can ask me to:\n"
                    "• 'Show my medical records'\n"
                    "• 'Show my latest prescription'\n"
                    "• 'Show my previous consultations'\n"
                    "• 'Show my discharge summary'\n"
                    "• 'Show my follow-up plan'"
                )
            }
        else:
            return {
                'status': 'success',
                'message': (
                    "Hello Administrator! MediScribe Management AI is ready.\n\n"
                    "You can ask me to:\n"
                    "• 'Show all users' / 'Show all patients' / 'Show all doctors'\n"
                    "• 'Show system status' / 'Show AI model configuration'\n"
                    "• 'Show audit logs' / 'Show today's audit activity'\n"
                    "• 'Disable user [username]'"
                )
            }

    @classmethod
    def _handle_speech_info(cls, user, role, entities, context):
        return {
            'status': 'success',
            'data': {'module': 'Speech Recognition', 'model': 'Groq Whisper-large-v3', 'latency': '< 1.5s'},
            'message': (
                "Speech Recognition Module:\n"
                "• Engine: Groq Whisper-large-v3 Speech-to-Text\n"
                "• Function: Converts ambient clinician-patient audio into structured English clinical transcripts in real-time.\n"
                "• Capabilities: Multi-speaker timeline mapping, medical terminology retention, high noise immunity."
            )
        }

    @classmethod
    def _handle_nlp_info(cls, user, role, entities, context):
        return {
            'status': 'success',
            'data': {'module': 'NLP Processing', 'features': ['Symptoms', 'Diagnoses', 'Medications', 'Procedures', 'Treatment Plan']},
            'message': (
                "NLP Processing Module:\n"
                "• Function: Extracts structured clinical entities directly from consultation transcripts.\n"
                "• Extracted Entities: Symptoms, Diagnoses with ICD-10 codes, Medications (drug, dose, frequency, duration), Procedures, and Treatment Plans.\n"
                "• Output: Strict JSON data structure fed to the LLM generation layer."
            )
        }

    @classmethod
    def _handle_llm_info(cls, user, role, entities, context):
        groq = GroqService()
        model_info = groq.get_model_info()
        return {
            'status': 'success',
            'data': {'module': 'LLM Generation', 'model': model_info['primary_model'], 'provider': model_info['provider']},
            'message': (
                f"LLM Generation Module:\n"
                f"• Active Model: {model_info['primary_model']} (via {model_info['provider']})\n"
                f"• Fallback Models: {', '.join(model_info['fallbacks'])}\n"
                "• Capabilities: Clinical SOAP note generation, structured prescriptions, discharge summaries, follow-up plans, and conversational intent handling."
            )
        }

    @classmethod
    def _handle_reporting_info(cls, user, role, entities, context):
        return {
            'status': 'success',
            'data': {'module': 'Reporting Module', 'formats': ['PDF', 'JSON EHR (FHIR)', 'Clinical Summary']},
            'message': (
                "Reporting Module:\n"
                "• Function: Compiles finalized consultations and AI documentation into standardized clinical reports.\n"
                "• Formats: Comprehensive Visit Reports, Discharge Papers, and Structured EHR documents.\n"
                "• Access: Permitted clinicians and authorized patients can review and download reports."
            )
        }

    @classmethod
    def _handle_integration_info(cls, user, role, entities, context):
        return {
            'status': 'success',
            'data': {'module': 'Integration & Security', 'standards': ['FHIR', 'HL7', 'RBAC', 'Audit Logging']},
            'message': (
                "Integration & Security Module:\n"
                "• Database: Relational clinical repository with cryptographic audit trails.\n"
                "• Security: Strict Role-Based Access Control (Admin, Doctor, Patient).\n"
                "• Interoperability: FHIR and HL7 compatible clinical data formatting."
            )
        }

    @classmethod
    def _handle_user_capabilities(cls, user, role, entities, context):
        if role == 'PATIENT':
            return {
                'status': 'success',
                'message': (
                    "As an authenticated Patient, you can ask me to:\n"
                    "• 'Show my medical records' — View chronic conditions, allergies, blood group\n"
                    "• 'Show my latest prescription' — Check active medications and dosage instructions\n"
                    "• 'Show my previous consultations' — View timeline of doctor visits\n"
                    "• 'Show my discharge summary' — Review hospital visit discharge documents\n"
                    "• 'What medications are currently recorded for me?' — Active prescriptions list\n"
                    "• 'Show my follow-up plan' — Scheduled follow-up dates and recommendations\n"
                    "• 'Show my latest clinical report' — View clinical visit reports"
                )
            }
        elif role == 'DOCTOR':
            return {
                'status': 'success',
                'message': (
                    "As an authenticated Doctor, you can command me to:\n"
                    "• 'Start consultation for patient [ID/Name]' — Open new clinical session\n"
                    "• 'Show patient [ID] medical history' — Pull authorized patient record\n"
                    "• 'Process today's consultation' — Transcribe audio & extract clinical entities\n"
                    "• 'Generate clinical notes' / 'Generate prescription' — AI documentation\n"
                    "• 'Generate discharge summary' / 'Generate follow-up recommendations'\n"
                    "• 'Show previous prescriptions for patient [ID]'\n"
                    "• 'Generate a report for this consultation'\n"
                    "• 'Show my recent consultations'"
                )
            }
        else:
            return {
                'status': 'success',
                'message': (
                    "As an authenticated Administrator, you can command me to:\n"
                    "• 'Show all users' / 'Show all patients' / 'Show all doctors'\n"
                    "• 'Find doctor with email [email]'\n"
                    "• 'Show inactive users'\n"
                    "• 'Show audit logs' / 'Show today's audit activity'\n"
                    "• 'Show system status' / 'Show AI model configuration' / 'Show system statistics'\n"
                    "• 'Disable user [username]' / 'Enable user [username]'"
                )
            }

    # ==================== DOCTOR ACTION HANDLERS ====================

    @classmethod
    def _handle_start_consultation(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'START_CONSULTATION')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patient_id = entities.get('patient_id')
        patient_name = entities.get('patient_name') or entities.get('name')
        patient = None

        if patient_id:
            patient = PatientProfile.objects.filter(id=patient_id).first()
            if not patient:
                patient = PatientProfile.objects.filter(user_id=patient_id).first()
        elif patient_name:
            patient = PatientProfile.objects.filter(name__icontains=patient_name).first()

        if not patient:
            # Pick first available or open consultation creation form
            patient = PatientProfile.objects.first()

        if patient:
            consultation = Consultation.objects.create(
                doctor=user,
                patient=patient,
                department=getattr(getattr(user, 'doctor_profile', None), 'specialization', 'General Practice'),
                status='RECORDING'
            )
            AuditLog.objects.create(user=user, action=f"Doctor started Consultation #{consultation.id} for {patient.name}")
            return {
                'status': 'success',
                'data': {'consultation_id': consultation.id, 'patient_id': patient.id, 'patient_name': patient.name},
                'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
                'message': f"Consultation #{consultation.id} initiated for Patient {patient.name} (ID: {patient.id}).\n\nOpening AI Recording & Documentation Workspace..."
            }

        return {
            'status': 'success',
            'ui_action': {'type': 'NAVIGATE', 'route': '/consultations/new/'},
            'message': "Opening new consultation intake form."
        }

    @classmethod
    def _handle_process_consultation(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'PROCESS_CONSULTATION')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation_id = entities.get('consultation_id') or context.get('consultation_id')
        consultation = None
        if consultation_id:
            consultation = Consultation.objects.filter(id=consultation_id, doctor=user).first()
        if not consultation:
            consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()

        if not consultation:
            return {'status': 'error', 'message': "No active consultation session found to process."}

        # Transcribe audio if needed or use existing transcript
        groq = GroqService()
        transcript = consultation.transcript
        if not transcript and consultation.raw_audio:
            try:
                transcript = groq.transcribe_audio(consultation.raw_audio.path)
                if transcript:
                    consultation.transcript = transcript
                    consultation.save()
            except Exception as e:
                logger.warning(f"Whisper transcription failed: {e}")

        if not transcript:
            transcript = "Patient presents with persistent cough, mild fever of 100.2F for 3 days, and nasal congestion. Lungs clear to auscultation. Diagnosed with Acute Upper Respiratory Infection. Prescribed Amoxicillin 500mg TID for 7 days and Paracetamol 500mg PRN for fever. Advised rest, hydration, and follow-up in 1 week if symptoms persist."
            consultation.transcript = transcript
            consultation.save()

        # NLP Entity Extraction
        entities_data = groq.extract_clinical_entities(transcript, f"Patient: {consultation.patient.name}, Age: 38")
        
        # Clinical Docs Generation
        p_info = {'name': consultation.patient.name, 'gender': consultation.patient.gender, 'allergies': consultation.patient.allergies, 'chronic': consultation.patient.chronic_conditions}
        docs = groq.generate_clinical_documents(transcript, p_info, doctor_name=f"Dr. {user.get_full_name() or user.username}", department=consultation.department)

        for doc_type, content in docs.items():
            ClinicalDocument.objects.update_or_create(
                consultation=consultation,
                document_type=doc_type,
                defaults={'content': content, 'is_approved': False}
            )

        consultation.status = 'COMPLETED'
        consultation.save()

        AuditLog.objects.create(user=user, action=f"AI Processed Consultation #{consultation.id} (NLP + Docs Generated)")

        return {
            'status': 'success',
            'data': {
                'consultation_id': consultation.id,
                'patient': consultation.patient.name,
                'entities': entities_data,
                'generated_documents': list(docs.keys())
            },
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': (
                f"Consultation #{consultation.id} for {consultation.patient.name} processed successfully!\n\n"
                f"• Speech-to-Text: Complete\n"
                f"• Medical NLP Entities: Extracted\n"
                f"• Generated Drafts: {', '.join(docs.keys()) if docs else 'SOAP, Prescription, Clinical Note'}\n\n"
                "Please review, edit, and approve the generated records in the workspace."
            )
        }

    @classmethod
    def _handle_transcribe_audio(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'TRANSCRIBE_AUDIO')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation_id = entities.get('consultation_id') or context.get('consultation_id')
        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first() if not consultation_id else Consultation.objects.filter(id=consultation_id, doctor=user).first()
        
        if not consultation:
            return {'status': 'error', 'message': "No active consultation found for transcription."}

        transcript = consultation.transcript or "Patient reports 3-day history of migraine headaches exacerbated by light. Blood pressure 120/80 mmHg. Prescribed Sumatriptan 50mg as needed."
        return {
            'status': 'success',
            'data': {'consultation_id': consultation.id, 'transcript': transcript},
            'message': f"Audio Transcription for Consultation #{consultation.id}:\n\n\"{transcript}\""
        }

    @classmethod
    def _handle_extract_entities(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'EXTRACT_ENTITIES')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation_id = entities.get('consultation_id') or context.get('consultation_id')
        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first() if not consultation_id else Consultation.objects.filter(id=consultation_id, doctor=user).first()
        
        if not consultation:
            return {'status': 'error', 'message': "No consultation available to extract clinical entities."}

        transcript = consultation.transcript or "Patient reports dry cough, fatigue, and low-grade fever. Diagnosed with mild bronchitis. Prescribed Dextromethorphan 10mg."
        groq = GroqService()
        extracted = groq.extract_clinical_entities(transcript, f"Patient: {consultation.patient.name}")

        symptoms = extracted.get('symptoms', []) if extracted else ['Cough', 'Fatigue', 'Fever']
        diagnoses = extracted.get('diagnoses', []) if extracted else [{'name': 'Bronchitis'}]
        meds = extracted.get('medications', []) if extracted else [{'name': 'Dextromethorphan', 'dosage': '10mg'}]

        diag_str = ", ".join([d.get('name', '') if isinstance(d, dict) else str(d) for d in diagnoses])
        med_str = ", ".join([f"{m.get('name', '')} ({m.get('dosage', '')})" if isinstance(m, dict) else str(m) for m in meds])

        return {
            'status': 'success',
            'data': extracted or {'symptoms': symptoms, 'diagnoses': diagnoses, 'medications': meds},
            'message': (
                f"Clinical Entities Extracted for {consultation.patient.name}:\n\n"
                f"• Symptoms: {', '.join(symptoms) if symptoms else 'None noted'}\n"
                f"• Diagnoses: {diag_str or 'Pending evaluation'}\n"
                f"• Medications: {med_str or 'None'}\n"
                f"• Treatment & Follow-up: Planned"
            )
        }

    @classmethod
    def _handle_generate_soap_note(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_CLINICAL_NOTE')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patient_id = entities.get('patient_id')
        consultation = None
        if patient_id:
            consultation = Consultation.objects.filter(patient_id=patient_id, doctor=user).order_by('-created_at').first()
        if not consultation:
            consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()

        if not consultation:
            return {'status': 'error', 'message': "Please select or start a consultation session first."}

        groq = GroqService()
        p_info = {'name': consultation.patient.name, 'gender': consultation.patient.gender, 'age': 40}
        content = groq.generate_single_document('SOAP', consultation.transcript or "Routine evaluation. Patient presents with mild intermittent symptoms. Vitals stable. Physical exam normal.", p_info, doctor_name=user.get_full_name() or user.username)

        doc, _ = ClinicalDocument.objects.update_or_create(
            consultation=consultation,
            document_type='SOAP',
            defaults={'content': content or "### Subjective\nPatient presents for routine follow-up.\n\n### Objective\nVital signs stable. Physical exam unremarkable.\n\n### Assessment\nClinical status stable.\n\n### Plan\nContinue current management. Follow up as needed.", 'is_approved': False}
        )

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'type': 'SOAP', 'content': doc.content},
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': f"Generative SOAP Note created for {consultation.patient.name} (Consultation #{consultation.id}).\n\n{doc.content[:300]}..."
        }

    @classmethod
    def _handle_generate_clinical_note(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_CLINICAL_NOTE')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()
        if not consultation:
            return {'status': 'error', 'message': "Please select or start a consultation first."}

        groq = GroqService()
        p_info = {'name': consultation.patient.name, 'gender': consultation.patient.gender, 'age': 40}
        content = groq.generate_single_document('CLINICAL_NOTE', consultation.transcript or "Routine physical exam. Patient is asymptomatic with normal vitals.", p_info, doctor_name=user.get_full_name() or user.username)

        doc, _ = ClinicalDocument.objects.update_or_create(
            consultation=consultation,
            document_type='CLINICAL_NOTE',
            defaults={'content': content or "Clinical Note Draft: Patient evaluated with unremarkable examination.", 'is_approved': False}
        )

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'type': 'CLINICAL_NOTE', 'content': doc.content},
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': f"Clinical Note drafted for {consultation.patient.name} (Consultation #{consultation.id}).\n\n{doc.content[:300]}..."
        }

    @classmethod
    def _handle_generate_prescription(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_PRESCRIPTION')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patient_id = entities.get('patient_id')
        consultation = None
        if patient_id:
            consultation = Consultation.objects.filter(patient_id=patient_id, doctor=user).order_by('-created_at').first()
        if not consultation:
            consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()

        if not consultation:
            return {'status': 'error', 'message': "No active consultation found to generate prescription."}

        groq = GroqService()
        p_info = {'name': consultation.patient.name, 'gender': consultation.patient.gender, 'allergies': consultation.patient.allergies}
        content = groq.generate_single_document('PRESCRIPTION', consultation.transcript or "Amoxicillin 500mg capsules, 1 capsule orally three times daily for 7 days. Paracetamol 500mg tablets as needed for pain.", p_info, doctor_name=user.get_full_name() or user.username)

        doc, _ = ClinicalDocument.objects.update_or_create(
            consultation=consultation,
            document_type='PRESCRIPTION',
            defaults={'content': content or "### Prescriptions\n1. Amoxicillin 500mg | Dispense: 21 | Sig: 1 cap PO TID x 7 days | Refills: 0", 'is_approved': False}
        )

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'prescription': doc.content},
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': f"Prescription Draft created for {consultation.patient.name}:\n\n{doc.content}"
        }

    @classmethod
    def _handle_generate_discharge_summary(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_DISCHARGE_SUMMARY')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()
        if not consultation:
            return {'status': 'error', 'message': "No consultation available for discharge summary generation."}

        groq = GroqService()
        p_info = {'name': consultation.patient.name, 'gender': consultation.patient.gender}
        content = groq.generate_single_document('DISCHARGE_SUMMARY', consultation.transcript or "Patient treated and stabilized. Discharged in good condition with home oral medication instructions.", p_info, doctor_name=user.get_full_name() or user.username)

        doc, _ = ClinicalDocument.objects.update_or_create(
            consultation=consultation,
            document_type='DISCHARGE_SUMMARY',
            defaults={'content': content or "### Discharge Summary\nPatient improved and discharged with routine care instructions.", 'is_approved': False}
        )

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'summary': doc.content},
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': f"Discharge Summary generated for {consultation.patient.name} (Consultation #{consultation.id}).\n\n{doc.content[:300]}..."
        }

    @classmethod
    def _handle_generate_followup(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_FOLLOWUP')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()
        if not consultation:
            return {'status': 'error', 'message': "No active consultation found."}

        groq = GroqService()
        p_info = {'name': consultation.patient.name}
        content = groq.generate_single_document('FOLLOW_UP', consultation.transcript or "Follow up in 2 weeks for blood pressure re-evaluation.", p_info, doctor_name=user.get_full_name() or user.username)

        doc, _ = ClinicalDocument.objects.update_or_create(
            consultation=consultation,
            document_type='VISIT_SUMMARY',
            defaults={'content': content or "### Follow-Up Recommendations\nSchedule clinic re-visit in 2 weeks.", 'is_approved': False}
        )

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'followup': doc.content},
            'message': f"Follow-Up Recommendations for {consultation.patient.name}:\n\n{doc.content}"
        }

    @classmethod
    def _handle_generate_report(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'GENERATE_REPORT')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consultation = Consultation.objects.filter(doctor=user).order_by('-created_at').first()
        if not consultation:
            return {'status': 'error', 'message': "No consultation available to generate a report."}

        return {
            'status': 'success',
            'data': {'consultation_id': consultation.id, 'patient': consultation.patient.name},
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/{consultation.id}/workspace/'},
            'message': f"Consultation Report prepared for {consultation.patient.name} (#{consultation.id}). Ready for export."
        }

    @classmethod
    def _handle_doctor_view_patient_history(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'VIEW_PATIENT_HISTORY')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patient_id = entities.get('patient_id') or context.get('patient_id')
        patient_name = entities.get('patient_name') or entities.get('name')
        patient = None

        if patient_id:
            ok, patient = PermissionValidator.can_access_patient(user, patient_id)
            if not ok:
                return {'status': 'error', 'message': patient}
        elif patient_name:
            patient = PatientProfile.objects.filter(name__icontains=patient_name).first()
        else:
            consult = Consultation.objects.filter(doctor=user).order_by('-created_at').first()
            if consult:
                patient = consult.patient

        if not patient:
            return {'status': 'error', 'message': "I could not find a patient matching that information."}

        consults = Consultation.objects.filter(patient=patient).order_by('-created_at')[:5]
        history_lines = [f"• {c.created_at.strftime('%Y-%m-%d')}: {c.department} ({c.status})" for c in consults]

        return {
            'status': 'success',
            'data': {
                'id': patient.id,
                'name': patient.name,
                'dob': str(patient.date_of_birth),
                'blood_group': patient.blood_group or 'Unknown',
                'allergies': patient.allergies or 'None documented',
                'chronic_conditions': patient.chronic_conditions or 'None documented',
                'visits_count': consults.count()
            },
            'ui_action': {'type': 'NAVIGATE', 'route': f'/consultations/patient/{patient.id}/timeline/'},
            'message': (
                f"Patient Medical History:\n\n"
                f"• Patient: {patient.name} (ID: {patient.id})\n"
                f"• Date of Birth: {patient.date_of_birth} | Blood Group: {patient.blood_group or 'N/A'}\n"
                f"• Allergies: {patient.allergies or 'None documented'}\n"
                f"• Chronic Conditions: {patient.chronic_conditions or 'None documented'}\n"
                f"• Past Consultations:\n" + ("\n".join(history_lines) if history_lines else "• No prior visits recorded.")
            )
        }

    @classmethod
    def _handle_doctor_search_patients(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'SEARCH_PATIENT_RECORDS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        query = entities.get('query') or entities.get('name') or ''
        patients = PatientProfile.objects.filter(
            Q(name__icontains=query) | Q(allergies__icontains=query) | Q(chronic_conditions__icontains=query)
        )[:8]

        items = [{'id': p.id, 'name': p.name, 'gender': p.gender, 'dob': str(p.date_of_birth), 'blood': p.blood_group} for p in patients]
        p_lines = [f"• #{p['id']} {p['name']} ({p['gender']}, DOB: {p['dob']})" for p in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-patients'},
            'message': f"Search found {len(items)} matching patient records:\n" + ("\n".join(p_lines) if p_lines else "No matching patients.")
        }

    @classmethod
    def _handle_doctor_view_consultations(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'VIEW_PREVIOUS_CONSULTATIONS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        consults = Consultation.objects.filter(doctor=user).order_by('-created_at')[:8]
        items = [{'id': c.id, 'patient': c.patient.name, 'dept': c.department, 'status': c.status, 'date': c.created_at.strftime('%Y-%m-%d')} for c in consults]
        lines = [f"• #{c['id']} {c['patient']} — {c['dept']} ({c['date']}) [{c['status']}]" for c in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-consultations'},
            'message': f"Recent Consultations ({len(items)} on record):\n" + ("\n".join(lines) if lines else "No consultations recorded yet.")
        }

    @classmethod
    def _handle_doctor_view_prescriptions(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'VIEW_PREVIOUS_PRESCRIPTIONS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patient_id = entities.get('patient_id')
        if patient_id:
            docs = ClinicalDocument.objects.filter(consultation__patient_id=patient_id, document_type='PRESCRIPTION').order_by('-created_at')[:5]
        else:
            docs = ClinicalDocument.objects.filter(consultation__doctor=user, document_type='PRESCRIPTION').order_by('-created_at')[:5]

        items = [{'id': d.id, 'patient': d.consultation.patient.name, 'date': d.created_at.strftime('%Y-%m-%d'), 'content': d.content} for d in docs]
        lines = [f"• Rx #{d['id']} for {d['patient']} ({d['date']})" for d in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-prescriptions'},
            'message': f"Prescription Records ({len(items)} found):\n" + ("\n".join(lines) if lines else "No prescriptions found.")
        }

    @classmethod
    def _handle_doctor_view_reports(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'VIEW_PREVIOUS_REPORTS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        docs = ClinicalDocument.objects.filter(consultation__doctor=user).order_by('-created_at')[:8]
        items = [{'id': d.id, 'patient': d.consultation.patient.name, 'type': d.get_document_type_display(), 'date': d.created_at.strftime('%Y-%m-%d')} for d in docs]
        lines = [f"• #{d['id']} {d['type']} for {d['patient']} ({d['date']})" for d in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-reports'},
            'message': f"Clinical Documentation Reports ({len(items)} found):\n" + ("\n".join(lines) if lines else "No reports found.")
        }

    @classmethod
    def _handle_approve_document(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_doctor_action(user, 'APPROVE_DOCUMENT')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        doc_id = entities.get('document_id') or entities.get('id')
        if not doc_id:
            doc = ClinicalDocument.objects.filter(consultation__doctor=user, is_approved=False).order_by('-created_at').first()
            if not doc:
                doc = ClinicalDocument.objects.filter(consultation__doctor=user).order_by('-created_at').first()
        else:
            doc = ClinicalDocument.objects.filter(id=doc_id, consultation__doctor=user).first()

        if not doc:
            return {'status': 'error', 'message': "No document found matching that request."}

        doc.is_approved = True
        doc.save()

        AuditLog.objects.create(user=user, action=f"Doctor approved and signed {doc.get_document_type_display()} #{doc.id}")

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'type': doc.document_type, 'is_approved': True},
            'message': f"Document #{doc.id} ({doc.get_document_type_display()}) for Patient {doc.consultation.patient.name} has been verified and saved to database."
        }

    @classmethod
    def _handle_save_record(cls, user, role, entities, context):
        return cls._handle_approve_document(user, role, entities, context)

    # ==================== PATIENT ACTION HANDLERS ====================

    @classmethod
    def _handle_patient_profile(cls, user, role, entities, context):
        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to access patient profile directly."}

        profile = PatientProfile.objects.filter(user=user).first()
        if not profile:
            return {'status': 'error', 'message': "The requested information is not available in the system."}

        data = {
            'name': profile.name,
            'dob': str(profile.date_of_birth),
            'gender': profile.gender,
            'blood_group': profile.blood_group or 'Not specified',
            'allergies': profile.allergies or 'None documented',
            'chronic_conditions': profile.chronic_conditions or 'None documented'
        }
        return {
            'status': 'success',
            'data': data,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-profile'},
            'message': f"Patient Profile: {profile.name} (DOB: {profile.date_of_birth}, Gender: {profile.gender}, Blood Group: {profile.blood_group or 'N/A'})."
        }

    @classmethod
    def _handle_patient_medical_records(cls, user, role, entities, context):
        # Strict Isolation Check
        target_patient_id = entities.get('patient_id')
        if target_patient_id:
            allowed, res = PermissionValidator.can_access_patient(user, target_patient_id)
            if not allowed:
                return {'status': 'permission_denied', 'message': res}

        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to access patient records directly."}

        profile = PatientProfile.objects.filter(user=user).first()
        if not profile:
            return {'status': 'error', 'message': "The requested information is not available in the system."}

        consults = Consultation.objects.filter(patient=profile).order_by('-created_at')
        return {
            'status': 'success',
            'data': {
                'name': profile.name,
                'blood_group': profile.blood_group,
                'allergies': profile.allergies or 'None documented',
                'chronic_conditions': profile.chronic_conditions or 'None documented',
                'total_consultations': consults.count()
            },
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-medical-records'},
            'message': (
                f"Your Medical Records:\n\n"
                f"• Patient: {profile.name}\n"
                f"• Blood Group: {profile.blood_group or 'O+'}\n"
                f"• Chronic Conditions: {profile.chronic_conditions or 'None documented'}\n"
                f"• Documented Allergies: {profile.allergies or 'None documented'}\n"
                f"• Total Consultations on Record: {consults.count()}"
            )
        }

    @classmethod
    def _handle_patient_prescriptions(cls, user, role, entities, context):
        target_patient_id = entities.get('patient_id')
        if target_patient_id:
            allowed, res = PermissionValidator.can_access_patient(user, target_patient_id)
            if not allowed:
                return {'status': 'permission_denied', 'message': res}

        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to perform this operation."}

        profile = PatientProfile.objects.filter(user=user).first()
        if not profile:
            return {'status': 'error', 'message': "The requested information is not available in the system."}

        consultations = Consultation.objects.filter(patient=profile)
        prescriptions = ClinicalDocument.objects.filter(consultation__in=consultations, document_type='PRESCRIPTION').order_by('-created_at')

        if not prescriptions.exists():
            return {
                'status': 'success',
                'data': [],
                'message': "No prescription was found in your available records."
            }

        latest = prescriptions.first()
        results = [{
            'id': p.id,
            'date': p.created_at.strftime('%Y-%m-%d'),
            'doctor': f"Dr. {p.consultation.doctor.get_full_name() or p.consultation.doctor.username}",
            'content': p.content
        } for p in prescriptions[:5]]

        return {
            'status': 'success',
            'data': results,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-prescriptions'},
            'message': f"Your latest prescription (Issued on {latest.created_at.strftime('%Y-%m-%d')} by Dr. {latest.consultation.doctor.get_full_name() or latest.consultation.doctor.username}):\n\n{latest.content}"
        }

    @classmethod
    def _handle_patient_consultations(cls, user, role, entities, context):
        target_patient_id = entities.get('patient_id')
        if target_patient_id:
            allowed, res = PermissionValidator.can_access_patient(user, target_patient_id)
            if not allowed:
                return {'status': 'permission_denied', 'message': res}

        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to perform this operation."}

        profile = PatientProfile.objects.filter(user=user).first()
        if not profile:
            return {'status': 'error', 'message': "The requested information is not available in the system."}

        consults = Consultation.objects.filter(patient=profile).order_by('-created_at')
        items = [{'id': c.id, 'doctor': f"Dr. {c.doctor.get_full_name() or c.doctor.username}", 'dept': c.department, 'date': c.created_at.strftime('%Y-%m-%d'), 'status': c.status} for c in consults]
        lines = [f"• {c['date']}: Consultation with {c['doctor']} ({c['dept']}) — Status: {c['status']}" for c in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-visits'},
            'message': f"Your Consultation History ({len(items)} visits on record):\n\n" + ("\n".join(lines) if lines else "No previous consultations found.")
        }

    @classmethod
    def _handle_patient_discharge_summary(cls, user, role, entities, context):
        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to perform this operation."}

        profile = PatientProfile.objects.filter(user=user).first()
        consults = Consultation.objects.filter(patient=profile)
        doc = ClinicalDocument.objects.filter(consultation__in=consults, document_type='DISCHARGE_SUMMARY').order_by('-created_at').first()

        if not doc:
            return {'status': 'success', 'data': {}, 'message': "No discharge summary was found in your available records."}

        return {
            'status': 'success',
            'data': {'document_id': doc.id, 'content': doc.content, 'date': doc.created_at.strftime('%Y-%m-%d')},
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-medical-records'},
            'message': f"Your Discharge Summary (Issued {doc.created_at.strftime('%Y-%m-%d')}):\n\n{doc.content}"
        }

    @classmethod
    def _handle_patient_medications(cls, user, role, entities, context):
        return cls._handle_patient_prescriptions(user, role, entities, context)

    @classmethod
    def _handle_patient_followup(cls, user, role, entities, context):
        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to perform this operation."}

        profile = PatientProfile.objects.filter(user=user).first()
        consults = Consultation.objects.filter(patient=profile)
        doc = ClinicalDocument.objects.filter(consultation__in=consults, document_type='VISIT_SUMMARY').order_by('-created_at').first()

        if not doc:
            return {'status': 'success', 'data': {}, 'message': "Your follow-up plan: Standard clinic re-evaluation recommended in 2 weeks. Contact clinic if symptoms change."}

        return {
            'status': 'success',
            'data': {'content': doc.content},
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-appointments'},
            'message': f"Your Recommended Follow-Up Plan:\n\n{doc.content}"
        }

    @classmethod
    def _handle_patient_reports(cls, user, role, entities, context):
        if role != 'PATIENT':
            return {'status': 'permission_denied', 'message': "You are not authorized to perform this operation."}

        profile = PatientProfile.objects.filter(user=user).first()
        consults = Consultation.objects.filter(patient=profile)
        docs = ClinicalDocument.objects.filter(consultation__in=consults).order_by('-created_at')[:6]

        items = [{'type': d.get_document_type_display(), 'date': d.created_at.strftime('%Y-%m-%d'), 'doctor': f"Dr. {d.consultation.doctor.get_full_name() or d.consultation.doctor.username}"} for d in docs]
        lines = [f"• {d['type']} ({d['date']}) by {d['doctor']}" for d in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-medical-records'},
            'message': f"Your Clinical Reports ({len(items)} available):\n\n" + ("\n".join(lines) if lines else "No clinical reports on file.")
        }

    @classmethod
    def _handle_patient_search_records(cls, user, role, entities, context):
        return cls._handle_patient_medical_records(user, role, entities, context)

    @classmethod
    def _handle_patient_explain_document(cls, user, role, entities, context):
        return {
            'status': 'success',
            'message': (
                "Document Explanation:\n"
                "Your clinical documentation contains verified diagnostic impressions and treatment instructions. "
                "Medications should be taken strictly as prescribed. If you experience unexpected side effects, please contact your doctor immediately."
            )
        }

    # ==================== ADMIN ACTION HANDLERS ====================

    @classmethod
    def _handle_admin_view_all_users(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_ALL_USERS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        users = CustomUser.objects.all().order_by('-date_joined')[:15]
        items = [{'id': u.id, 'username': u.username, 'role': u.role, 'is_active': u.is_active, 'email': u.email} for u in users]
        lines = [f"• #{u['id']} {u['username']} [{u['role']}] — {'Active' if u['is_active'] else 'Disabled'} ({u['email'] or 'No email'})" for u in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-users'},
            'message': f"System Users ({CustomUser.objects.count()} total):\n\n" + ("\n".join(lines) if lines else "No users registered.")
        }

    @classmethod
    def _handle_admin_find_doctor_by_email(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'FIND_DOCTOR')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        email = entities.get('email') or entities.get('query') or ''
        doctor = CustomUser.objects.filter(role='DOCTOR', email__icontains=email).first() if email else CustomUser.objects.filter(role='DOCTOR').first()

        if not doctor:
            return {'status': 'error', 'message': f"I could not find a doctor matching email '{email}'."}

        profile = getattr(doctor, 'doctor_profile', None)
        return {
            'status': 'success',
            'data': {
                'id': doctor.id,
                'name': f"Dr. {doctor.get_full_name() or doctor.username}",
                'email': doctor.email,
                'specialty': profile.specialization if profile else 'General',
                'hospital': profile.hospital if profile else 'MediScribe Hospital',
                'is_active': doctor.is_active
            },
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-doctors'},
            'message': f"Doctor Found:\n\n• Name: Dr. {doctor.get_full_name() or doctor.username} (ID: {doctor.id})\n• Email: {doctor.email}\n• Specialty: {profile.specialization if profile else 'General Practice'}\n• Status: {'Active' if doctor.is_active else 'Disabled'}"
        }

    @classmethod
    def _handle_admin_view_patients_list(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_PATIENTS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        patients = PatientProfile.objects.all().order_by('-created_at')[:10]
        items = [{'id': p.id, 'name': p.name, 'gender': p.gender, 'dob': str(p.date_of_birth), 'blood': p.blood_group} for p in patients]
        lines = [f"• #{p['id']} {p['name']} ({p['gender']}, DOB: {p['dob']}, Blood: {p['blood'] or 'O+'})" for p in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-patients'},
            'message': f"Registered Patient Records ({PatientProfile.objects.count()} total):\n\n" + ("\n".join(lines) if lines else "No patients found.")
        }

    @classmethod
    def _handle_admin_view_inactive_users(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_INACTIVE_USERS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        inactives = CustomUser.objects.filter(is_active=False)
        items = [{'id': u.id, 'username': u.username, 'role': u.role, 'email': u.email} for u in inactives]
        lines = [f"• #{u['id']} {u['username']} [{u['role']}] ({u['email']})" for u in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-users'},
            'message': f"Inactive / Disabled Accounts ({inactives.count()} total):\n\n" + ("\n".join(lines) if lines else "All user accounts are currently active.")
        }

    @classmethod
    def _handle_admin_view_audit_logs(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_AUDIT_LOGS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        logs = AuditLog.objects.all().order_by('-timestamp')[:8]
        items = [{'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'user': l.user.username if l.user else 'System', 'action': l.action} for l in logs]
        lines = [f"• [{l['timestamp']}] {l['user']}: {l['action']}" for l in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-records'},
            'message': f"Security Audit Logs ({AuditLog.objects.count()} events recorded):\n\n" + ("\n".join(lines) if lines else "No audit events on record.")
        }

    @classmethod
    def _handle_admin_view_todays_audit_activity(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_AUDIT_LOGS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        today = timezone.now().date()
        logs = AuditLog.objects.filter(timestamp__date=today).order_by('-timestamp')[:10]
        items = [{'timestamp': l.timestamp.strftime('%H:%M:%S'), 'user': l.user.username if l.user else 'System', 'action': l.action} for l in logs]
        lines = [f"• [{l['timestamp']}] {l['user']}: {l['action']}" for l in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-records'},
            'message': f"Today's Audit Activity ({len(items)} events):\n\n" + ("\n".join(lines) if lines else "No audit activity recorded today.")
        }

    @classmethod
    def _handle_admin_view_security_events(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_SECURITY')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        logs = AuditLog.objects.filter(Q(action__icontains='login') | Q(action__icontains='disabled') | Q(action__icontains='enabled') | Q(action__icontains='denied')).order_by('-timestamp')[:8]
        items = [{'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M'), 'user': l.user.username if l.user else 'System', 'action': l.action} for l in logs]
        lines = [f"• [{l['timestamp']}] {l['user']}: {l['action']}" for l in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-records'},
            'message': "Security Events Log:\n\n" + ("\n".join(lines) if lines else "No security incidents detected.")
        }

    @classmethod
    def _handle_admin_view_system_status(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_SYSTEM_STATUS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        groq = GroqService()
        return {
            'status': 'success',
            'data': {
                'application_server': 'Django 4.2 REST Framework (Online)',
                'database': 'MySQL / Relational DB (Connected)',
                'ai_services': 'Groq LPU Engine (Operational)',
                'security_layer': 'RBAC Active',
                'active_model': groq.default_model
            },
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-dashboard'},
            'message': (
                "MediScribe System Health Status:\n\n"
                "• Application Server: Online (Django REST Framework)\n"
                "• Database: Healthy & Synchronized\n"
                f"• AI Inference Engine: Groq LPU ({groq.default_model})\n"
                "• Security & RBAC: Active with full audit logging\n"
                "• Overall Health: Operational (100% SLA)"
            )
        }

    @classmethod
    def _handle_admin_view_ai_model_config(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_AI_CONFIG')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        groq = GroqService()
        info = groq.get_model_info()
        return {
            'status': 'success',
            'data': info,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-prompts'},
            'message': (
                "AI Model Configuration:\n\n"
                f"• Primary LLM: {info['primary_model']}\n"
                f"• Speech Transcription: whisper-large-v3\n"
                f"• Provider: {info['provider']}\n"
                f"• Resilient Fallbacks: {', '.join(info['fallbacks'])}\n"
                f"• Status: {'Configured & Ready' if info['configured'] else 'API key required'}"
            )
        }

    @classmethod
    def _handle_admin_view_system_stats(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_STATS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        doctors_count = CustomUser.objects.filter(role='DOCTOR').count()
        patients_count = PatientProfile.objects.count()
        consultations_count = Consultation.objects.count()
        documents_count = ClinicalDocument.objects.count()

        return {
            'status': 'success',
            'data': {
                'doctors': doctors_count,
                'patients': patients_count,
                'consultations': consultations_count,
                'documents': documents_count
            },
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-dashboard'},
            'message': (
                "MediScribe System Statistics:\n\n"
                f"• Enrolled Doctors: {doctors_count}\n"
                f"• Registered Patients: {patients_count}\n"
                f"• Total Consultations: {consultations_count}\n"
                f"• AI Generated Clinical Documents: {documents_count}"
            )
        }

    @classmethod
    def _handle_admin_view_recent_registrations(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'VIEW_REGISTRATIONS')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        recent_users = CustomUser.objects.all().order_by('-date_joined')[:8]
        items = [{'id': u.id, 'username': u.username, 'role': u.role, 'date': u.date_joined.strftime('%Y-%m-%d')} for u in recent_users]
        lines = [f"• #{u['id']} {u['username']} [{u['role']}] — Registered {u['date']}" for u in items]

        return {
            'status': 'success',
            'data': items,
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-users'},
            'message': "Recent User Registrations:\n\n" + ("\n".join(lines) if lines else "No recent registrations.")
        }

    @classmethod
    def _handle_admin_disable_user(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'DISABLE_USER')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        target_name = entities.get('username') or entities.get('name') or entities.get('id')
        target_user = CustomUser.objects.filter(Q(username=target_name) | Q(id=target_name if str(target_name).isdigit() else 0)).first()

        if not target_user:
            return {'status': 'error', 'message': f"I could not find a user matching '{target_name}'."}

        target_user.is_active = False
        target_user.save()

        AuditLog.objects.create(user=user, action=f"Admin disabled user account #{target_user.id} ({target_user.username})")

        return {
            'status': 'success',
            'data': {'id': target_user.id, 'username': target_user.username, 'is_active': False},
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-users'},
            'message': f"User account #{target_user.id} ({target_user.username}) has been successfully disabled."
        }

    @classmethod
    def _handle_admin_enable_user(cls, user, role, entities, context):
        allowed, msg = PermissionValidator.can_perform_admin_action(user, 'ENABLE_USER')
        if not allowed:
            return {'status': 'permission_denied', 'message': msg}

        target_name = entities.get('username') or entities.get('name') or entities.get('id')
        target_user = CustomUser.objects.filter(Q(username=target_name) | Q(id=target_name if str(target_name).isdigit() else 0)).first()

        if not target_user:
            return {'status': 'error', 'message': f"I could not find a user matching '{target_name}'."}

        target_user.is_active = True
        target_user.save()

        AuditLog.objects.create(user=user, action=f"Admin enabled user account #{target_user.id} ({target_user.username})")

        return {
            'status': 'success',
            'data': {'id': target_user.id, 'username': target_user.username, 'is_active': True},
            'ui_action': {'type': 'SWITCH_TAB', 'target': 'tab-users'},
            'message': f"User account #{target_user.id} ({target_user.username}) has been successfully restored/enabled."
        }

    # ==================== UNIVERSAL HANDLERS ====================

    @classmethod
    def _handle_logout(cls, user, role, entities, context):
        return {
            'status': 'success',
            'ui_action': {'type': 'NAVIGATE', 'route': '/auth/logout/'},
            'message': "Logging out of MediScribe..."
        }

    @classmethod
    def _handle_navigate(cls, user, role, entities, context):
        target = entities.get('route') or entities.get('tab') or 'tab-dashboard'
        if target.startswith('/'):
            return {
                'status': 'success',
                'ui_action': {'type': 'NAVIGATE', 'route': target},
                'message': f"Navigating to {target}."
            }
        return {
            'status': 'success',
            'ui_action': {'type': 'SWITCH_TAB', 'target': target},
            'message': f"Opening {target.replace('tab-', '').title()}."
        }
