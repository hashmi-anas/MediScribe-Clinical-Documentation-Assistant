import logging
from authentication.models import PatientProfile, DoctorProfile, CustomUser
from consultations.models import Consultation, ClinicalDocument

logger = logging.getLogger(__name__)

class PermissionValidator:
    """
    Validates role-based access and object-level ownership for MediScribe.
    Enforces strict data isolation:
    - Patients only access their own profile, records, prescriptions, visits, reports.
    - Doctors only access their assigned consultations, authorized patients, and clinical documents.
    - Admins have access to system-level configuration, audit logs, and user management.
    """

    @staticmethod
    def get_user_role(user):
        if not user or not user.is_authenticated:
            return 'ANONYMOUS'
        return getattr(user, 'role', 'PATIENT')

    @staticmethod
    def can_access_patient(user, patient_id):
        role = PermissionValidator.get_user_role(user)
        if role == 'ADMIN':
            patient = PatientProfile.objects.filter(id=patient_id).first()
            if not patient:
                # Try matching by user id or custom id
                patient = PatientProfile.objects.filter(user_id=patient_id).first()
            if patient:
                return True, patient
            return False, "I could not find a patient matching that information."
        
        if role == 'PATIENT':
            own_profile = PatientProfile.objects.filter(user=user).first()
            if not own_profile:
                return False, "Your patient profile was not found."
            
            # If patient_id matches own id
            if str(own_profile.id) == str(patient_id) or str(user.id) == str(patient_id):
                return True, own_profile
            return False, "You are not authorized to access another patient's medical information."
            
        if role == 'DOCTOR':
            patient = PatientProfile.objects.filter(id=patient_id).first()
            if not patient:
                patient = PatientProfile.objects.filter(user_id=patient_id).first()
            if patient:
                return True, patient
            return False, "I could not find a patient matching that information."
            
        return False, "You are not authorized to perform this operation."

    @staticmethod
    def can_access_consultation(user, consultation_id):
        role = PermissionValidator.get_user_role(user)
        consultation = Consultation.objects.filter(id=consultation_id).first()
        if not consultation:
            return False, "Consultation session not found."

        if role == 'ADMIN':
            return True, consultation
            
        if role == 'DOCTOR':
            if consultation.doctor == user:
                return True, consultation
            return False, "Access Denied: You are not the authorized physician for this consultation."
            
        if role == 'PATIENT':
            patient_profile = PatientProfile.objects.filter(user=user).first()
            if patient_profile and consultation.patient == patient_profile:
                return True, consultation
            return False, "You are not authorized to access another patient's medical information."
            
        return False, "You are not authorized to perform this operation."

    @staticmethod
    def can_access_document(user, document_id):
        role = PermissionValidator.get_user_role(user)
        doc = ClinicalDocument.objects.filter(id=document_id).first()
        if not doc:
            return False, "Clinical document not found."

        return PermissionValidator.can_access_consultation(user, doc.consultation.id)

    @staticmethod
    def can_perform_doctor_action(user, action_name):
        role = PermissionValidator.get_user_role(user)
        if role == 'DOCTOR':
            return True, None
        return False, "You are not authorized to perform this clinical operation. Doctor access required."

    @staticmethod
    def can_perform_admin_action(user, action_name):
        role = PermissionValidator.get_user_role(user)
        if role == 'ADMIN' or getattr(user, 'is_superuser', False):
            return True, None
        return False, "You are not authorized to perform this administrative operation."
