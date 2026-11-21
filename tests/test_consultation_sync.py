from django.test import TestCase, Client
from django.urls import reverse
from authentication.models import CustomUser, DoctorProfile, PatientProfile
from consultations.models import Consultation, ConsultationMessage, ClinicalDocument

class BidirectionalConsultationSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create Doctor
        self.doctor_user = CustomUser.objects.create_user(
            username='dr_smith',
            password='Password123!',
            first_name='John',
            last_name='Smith',
            role='DOCTOR'
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialization='Cardiology',
            hospital='MediScribe City Hospital'
        )
        
        # Create Patient 1
        self.patient_user1 = CustomUser.objects.create_user(
            username='alice_patient',
            password='Password123!',
            first_name='Alice',
            last_name='Williams',
            role='PATIENT'
        )
        self.patient_profile1 = PatientProfile.objects.create(
            user=self.patient_user1,
            name='Alice Williams',
            date_of_birth='1995-04-12',
            gender='Female',
            blood_group='A+'
        )

        # Create Patient 2 (for permission testing)
        self.patient_user2 = CustomUser.objects.create_user(
            username='bob_patient',
            password='Password123!',
            first_name='Bob',
            last_name='Brown',
            role='PATIENT'
        )
        self.patient_profile2 = PatientProfile.objects.create(
            user=self.patient_user2,
            name='Bob Brown',
            date_of_birth='1988-11-05',
            gender='Male',
            blood_group='O+'
        )

    def test_patient_can_start_consultation(self):
        """Test that a patient can initiate a new consultation with a doctor."""
        self.client.login(username='alice_patient', password='Password123!')
        
        response = self.client.post(reverse('new_consultation'), {
            'action': 'patient_start',
            'doctor_id': self.doctor_profile.id,
            'department': 'Cardiology',
            'visit_type': 'Outpatient Consultation',
            'language': 'English',
            'reason': 'Experiencing mild palpitations after light workouts.'
        })
        
        # Should redirect to consultation room
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.filter(patient=self.patient_profile1).latest('created_at')
        self.assertEqual(consultation.doctor, self.doctor_user)
        self.assertEqual(consultation.department, 'Cardiology')
        self.assertIn(f'/consultations/{consultation.id}/room/', response.url)
        
        # Check that the initial message was saved
        initial_msg = ConsultationMessage.objects.filter(consultation=consultation).first()
        self.assertIsNotNone(initial_msg)
        self.assertEqual(initial_msg.speaker, 'Patient')
        self.assertIn('mild palpitations', initial_msg.text)

    def test_doctor_can_start_consultation(self):
        """Test that a doctor can initiate a new consultation with a patient."""
        self.client.login(username='dr_smith', password='Password123!')
        
        response = self.client.post(reverse('new_consultation'), {
            'action': 'select_patient',
            'patient_id': self.patient_profile1.id,
            'department': 'Cardiology',
            'visit_type': 'Outpatient Consultation',
            'language': 'English',
            'specialty': 'General Practice'
        })
        
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.filter(patient=self.patient_profile1, doctor=self.doctor_user).latest('created_at')
        self.assertIn(f'/consultations/{consultation.id}/workspace/', response.url)

    def test_bidirectional_message_sync(self):
        """Test real-time message sending and sync from both sides."""
        consultation = Consultation.objects.create(
            doctor=self.doctor_user,
            patient=self.patient_profile1,
            department='Cardiology',
            status='RECORDING'
        )

        # 1. Patient sends a message
        self.client.login(username='alice_patient', password='Password123!')
        res_patient = self.client.post(reverse('consultation_send_message', args=[consultation.id]), {
            'speaker': 'Patient',
            'text': 'Hello Dr. Smith, I have been feeling dizzy this morning.'
        })
        self.assertEqual(res_patient.status_code, 200)
        data_p = res_patient.json()
        self.assertEqual(data_p['status'], 'success')
        self.assertEqual(data_p['message']['speaker'], 'Patient')
        patient_msg_id = data_p['message']['id']

        # 2. Doctor syncs and sees the patient message
        self.client.login(username='dr_smith', password='Password123!')
        sync_res_doc = self.client.get(f"{reverse('consultation_sync', args=[consultation.id])}?last_id=0")
        self.assertEqual(sync_res_doc.status_code, 200)
        sync_data_doc = sync_res_doc.json()
        self.assertEqual(len(sync_data_doc['messages']), 1)
        self.assertEqual(sync_data_doc['messages'][0]['text'], 'Hello Dr. Smith, I have been feeling dizzy this morning.')
        self.assertFalse(sync_data_doc['messages'][0]['is_self'])

        # 3. Doctor sends a reply
        res_doctor = self.client.post(reverse('consultation_send_message', args=[consultation.id]), {
            'speaker': 'Doctor',
            'text': 'Hello Alice, let us check your blood pressure and heart rate.'
        })
        self.assertEqual(res_doctor.status_code, 200)
        data_d = res_doctor.json()
        self.assertEqual(data_d['status'], 'success')
        doctor_msg_id = data_d['message']['id']

        # 4. Patient syncs with last_id = patient_msg_id to receive only the new doctor message
        self.client.login(username='alice_patient', password='Password123!')
        sync_res_pat = self.client.get(f"{reverse('consultation_sync', args=[consultation.id])}?last_id={patient_msg_id}")
        self.assertEqual(sync_res_pat.status_code, 200)
        sync_data_pat = sync_res_pat.json()
        self.assertEqual(len(sync_data_pat['messages']), 1)
        self.assertEqual(sync_data_pat['messages'][0]['speaker'], 'Doctor')
        self.assertEqual(sync_data_pat['messages'][0]['text'], 'Hello Alice, let us check your blood pressure and heart rate.')

        # 5. Verify full consultation transcript
        consultation.refresh_from_db()
        self.assertIn('Patient: Hello Dr. Smith', consultation.transcript)
        self.assertIn('Doctor: Hello Alice', consultation.transcript)

    def test_unauthorized_user_cannot_access_or_sync_consultation(self):
        """Test security isolation: Bob cannot access or sync Alice's consultation."""
        consultation = Consultation.objects.create(
            doctor=self.doctor_user,
            patient=self.patient_profile1,
            department='Cardiology',
            status='RECORDING'
        )

        self.client.login(username='bob_patient', password='Password123!')

        # Bob attempts to view consultation room
        room_res = self.client.get(reverse('consultation_room', args=[consultation.id]))
        self.assertEqual(room_res.status_code, 403)

        # Bob attempts to sync consultation
        sync_res = self.client.get(reverse('consultation_sync', args=[consultation.id]))
        self.assertEqual(sync_res.status_code, 403)

        # Bob attempts to send message to consultation
        msg_res = self.client.post(reverse('consultation_send_message', args=[consultation.id]), {
            'speaker': 'Patient',
            'text': 'Unauthorized attempt'
        })
        self.assertEqual(msg_res.status_code, 403)

    def test_notifications_dispatched_on_consultation_and_messages(self):
        """Test that doctor and patient get instant notification alerts on consultation start and messages."""
        from consultations.models import Notification

        # 1. Doctor starts consultation -> Patient receives notification
        self.client.login(username='dr_smith', password='Password123!')
        self.client.post(reverse('new_consultation'), {
            'action': 'select_patient',
            'patient_id': self.patient_profile1.id,
            'department': 'Cardiology'
        })
        
        patient_notif = Notification.objects.filter(user=self.patient_user1, is_read=False).first()
        self.assertIsNotNone(patient_notif)
        self.assertIn('Dr. John Smith', patient_notif.message)
        self.assertIn('/consultations/', patient_notif.action_url)

        # 2. Patient polls unread notifications endpoint
        self.client.login(username='alice_patient', password='Password123!')
        res_poll = self.client.get(reverse('get_unread_notifications'))
        self.assertEqual(res_poll.status_code, 200)
        data_poll = res_poll.json()
        self.assertGreaterEqual(data_poll['count'], 1)
        self.assertEqual(data_poll['notifications'][0]['id'], patient_notif.id)

        # 3. Patient marks notification as read
        res_read = self.client.post(reverse('mark_notification_read'), {'notification_id': patient_notif.id})
        self.assertEqual(res_read.status_code, 200)
        patient_notif.refresh_from_db()
        self.assertTrue(patient_notif.is_read)

        # 4. Patient starts consultation -> Doctor receives notification
        self.client.post(reverse('new_consultation'), {
            'action': 'patient_start',
            'doctor_id': self.doctor_profile.id,
            'department': 'Cardiology',
            'reason': 'Checkup after surgery'
        })

        doctor_notif = Notification.objects.filter(user=self.doctor_user, is_read=False).first()
        self.assertIsNotNone(doctor_notif)
        self.assertIn('Alice Williams', doctor_notif.message)
        self.assertIn('/workspace/', doctor_notif.action_url)

