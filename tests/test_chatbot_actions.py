import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from authentication.models import CustomUser, DoctorProfile, PatientProfile
from consultations.models import Consultation, ClinicalDocument, AuditLog
from services.ai_agent import AIAgent
from services.action_executor import ActionExecutor
from services.permissions import PermissionValidator

class MediScribeChatbotTestSuite(TestCase):
    def setUp(self):
        # 1. Setup Admin User
        self.admin_user = CustomUser.objects.create_user(
            username='admin_test',
            email='admin@mediscribe.com',
            password='Password123!',
            role='ADMIN'
        )

        # 2. Setup Doctor User & Profile
        self.doc_user = CustomUser.objects.create_user(
            username='dr_smith',
            email='smith@mediscribe.com',
            password='Password123!',
            first_name='John',
            last_name='Smith',
            role='DOCTOR'
        )
        self.doc_profile = DoctorProfile.objects.create(
            user=self.doc_user,
            specialization='Cardiology',
            hospital='MediScribe Central Hospital'
        )

        # 3. Setup Patient 1 (Alice)
        self.pat1_user = CustomUser.objects.create_user(
            username='alice_pat',
            email='alice@example.com',
            password='Password123!',
            first_name='Alice',
            last_name='Johnson',
            role='PATIENT'
        )
        self.pat1_profile = PatientProfile.objects.create(
            user=self.pat1_user,
            name='Alice Johnson',
            date_of_birth=datetime.date(1992, 4, 15),
            gender='Female',
            blood_group='A+',
            allergies='Penicillin',
            chronic_conditions='Hypertension'
        )

        # 4. Setup Patient 2 (Bob)
        self.pat2_user = CustomUser.objects.create_user(
            username='bob_pat',
            email='bob@example.com',
            password='Password123!',
            first_name='Bob',
            last_name='Williams',
            role='PATIENT'
        )
        self.pat2_profile = PatientProfile.objects.create(
            user=self.pat2_user,
            name='Bob Williams',
            date_of_birth=datetime.date(1985, 8, 22),
            gender='Male',
            blood_group='O+',
            allergies='Sulfa',
            chronic_conditions='None'
        )

        # 5. Create Consultation & Documents for Alice
        self.consultation_alice = Consultation.objects.create(
            doctor=self.doc_user,
            patient=self.pat1_profile,
            department='Cardiology',
            transcript='Patient reports mild chest tightness after exercise. BP 130/85. Prescribed Metoprolol 25mg daily.',
            status='COMPLETED'
        )
        self.rx_alice = ClinicalDocument.objects.create(
            consultation=self.consultation_alice,
            document_type='PRESCRIPTION',
            content='### Prescriptions\n1. Metoprolol 25mg | Dispense: 30 | Sig: 1 tab PO daily',
            is_approved=True
        )
        self.note_alice = ClinicalDocument.objects.create(
            consultation=self.consultation_alice,
            document_type='CLINICAL_NOTE',
            content='### Clinical Impression\nStage 1 hypertension with mild exertional symptoms.',
            is_approved=True
        )

        self.ai_agent = AIAgent()
        self.client = Client()

    # ==================== DOCTOR CHATBOT TESTS ====================

    def test_doctor_start_consultation(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query=f"Start consultation for patient {self.pat1_profile.id}"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'START_CONSULTATION')
        self.assertIn('Consultation #', res.get('message'))

    def test_doctor_view_patient_history(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query=f"Show patient {self.pat1_profile.id} medical history"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_PATIENT_HISTORY')
        self.assertIn('Alice Johnson', res.get('message'))
        self.assertIn('Penicillin', res.get('message'))

    def test_doctor_process_consultation(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="Process today's consultation"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'PROCESS_CONSULTATION')

    def test_doctor_generate_prescription(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query=f"Generate prescription for patient {self.pat1_profile.id}"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'GENERATE_PRESCRIPTION')
        self.assertIn('Prescription Draft', res.get('message'))

    def test_doctor_generate_clinical_notes(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="Generate clinical notes"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'GENERATE_CLINICAL_NOTE')

    def test_doctor_generate_discharge_summary(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="Generate discharge summary"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'GENERATE_DISCHARGE_SUMMARY')

    def test_doctor_approve_document(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="Save this clinical note"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'APPROVE_DOCUMENT')

    # ==================== PATIENT CHATBOT TESTS ====================

    def test_patient_view_own_medical_records(self):
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query="Show my medical records"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_OWN_MEDICAL_RECORDS')
        self.assertIn('Alice Johnson', res.get('message'))
        self.assertIn('Hypertension', res.get('message'))

    def test_patient_view_own_prescription(self):
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query="Show my latest prescription"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_OWN_PRESCRIPTIONS')
        self.assertIn('Metoprolol', res.get('message'))

    def test_patient_isolation_another_patient_denied(self):
        # Alice tries to query Bob's records (ID of pat2_profile)
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query=f"Show patient {self.pat2_profile.id} records"
        )
        self.assertFalse(res.get('success'))
        self.assertEqual(res.get('status'), 'permission_denied')
        self.assertIn("You are not authorized to access another patient's medical information", res.get('message'))

    def test_patient_cannot_execute_admin_command(self):
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query="Show all users"
        )
        # Should route through patient safe boundaries or reject admin access
        self.assertNotIn('admin_test', res.get('message'))

    # ==================== ADMIN CHATBOT TESTS ====================

    def test_admin_view_all_users(self):
        res = self.ai_agent.process_request(
            user=self.admin_user,
            query="Show all users"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_ALL_USERS')
        self.assertIn('admin_test', res.get('message'))
        self.assertIn('dr_smith', res.get('message'))

    def test_admin_find_doctor_by_email(self):
        res = self.ai_agent.process_request(
            user=self.admin_user,
            query="Find doctor with email smith@mediscribe.com"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'FIND_DOCTOR_BY_EMAIL')
        self.assertIn('smith@mediscribe.com', res.get('message'))

    def test_admin_view_audit_logs(self):
        res = self.ai_agent.process_request(
            user=self.admin_user,
            query="Show audit logs"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_AUDIT_LOGS')

    def test_admin_view_system_status(self):
        res = self.ai_agent.process_request(
            user=self.admin_user,
            query="Show system status"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'VIEW_SYSTEM_STATUS')
        self.assertIn('Operational', res.get('message'))

    def test_admin_disable_user_requires_confirmation(self):
        res = self.ai_agent.process_request(
            user=self.admin_user,
            query="Disable user bob_pat"
        )
        self.assertEqual(res.get('status'), 'confirmation_required')
        self.assertIn('bob_pat', res.get('message'))

        # Now confirm action
        confirm_res = self.ai_agent.process_request(
            user=self.admin_user,
            query="",
            confirmed_action={'action_name': 'DISABLE_USER', 'entities': {'username': 'bob_pat'}}
        )
        self.assertTrue(confirm_res.get('success'))
        self.pat2_user.refresh_from_db()
        self.assertFalse(self.pat2_user.is_active)

    # ==================== KEYWORD & MODULE QUESTIONS ====================

    def test_keyword_speech_recognition_focused(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="speech recognition"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'SPEECH_RECOGNITION_INFO')
        self.assertIn('Speech Recognition Module', res.get('message'))
        self.assertNotIn('Admin', res.get('message'))

    def test_keyword_what_is_nlp(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="What is NLP?"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'NLP_PROCESSING_INFO')
        self.assertIn('NLP Processing Module', res.get('message'))

    def test_keyword_what_can_i_do(self):
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query="What can I do?"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'USER_CAPABILITIES')
        self.assertIn('Show my medical records', res.get('message'))

    def test_greeting_doctor(self):
        res = self.ai_agent.process_request(
            user=self.doc_user,
            query="hii"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'GREETING')
        self.assertIn('Dr. John Smith', res.get('message'))

    def test_greeting_patient(self):
        res = self.ai_agent.process_request(
            user=self.pat1_user,
            query="hello"
        )
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('intent'), 'GREETING')
        self.assertIn('Alice Johnson', res.get('message'))

    # ==================== REST API ENDPOINT TESTS ====================

    def test_api_chatbot_message_endpoint(self):
        self.client.force_login(self.pat1_user)
        response = self.client.post('/api/chatbot/message/', data={'message': 'Show my latest prescription'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('intent'), 'VIEW_OWN_PRESCRIPTIONS')

    def test_api_system_status_endpoint(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/system/status/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('status'), 'Operational')

    def test_admin_dashboard_view_renders(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/admin/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Advanced Platform Analytics', response.content.decode('utf-8'))

    def test_doctor_dashboard_view_renders(self):
        self.client.force_login(self.doc_user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Consultations Overview', response.content.decode('utf-8'))

