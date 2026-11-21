from django.db import models
from django.conf import settings
from authentication.models import PatientProfile

class Consultation(models.Model):
    STATUS_CHOICES = (
        ('RECORDING', 'Recording'),
        ('PROCESSING', 'AI Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consultations')
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='consultations')
    department = models.CharField(max_length=100, default='Cardiology')
    visit_type = models.CharField(max_length=50, default='Outpatient Visit')
    language = models.CharField(max_length=50, default='English')
    specialty = models.CharField(max_length=100, default='General Practice')
    
    raw_audio = models.FileField(upload_to='consultation_audios/', blank=True, null=True)
    raw_video = models.FileField(upload_to='consultation_videos/', blank=True, null=True)
    
    transcript = models.TextField(blank=True, null=True)
    transcription_confidence = models.FloatField(default=1.0)
    speaker_timeline = models.JSONField(blank=True, null=True) # speaker segments
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RECORDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Consultation on {self.created_at.strftime('%Y-%m-%d %H:%M')} - Doctor: {self.doctor} - Patient: {self.patient}"

class ClinicalDocument(models.Model):
    DOC_TYPES = (
        ('SOAP', 'SOAP Note'),
        ('CLINICAL_NOTE', 'Clinical Note'),
        ('PRESCRIPTION', 'Prescription Draft'),
        ('DISCHARGE_SUMMARY', 'Discharge Summary'),
        ('VISIT_SUMMARY', 'Visit Summary'),
        ('EHR_STRUCTURED', 'Structured EHR (FHIR/HL7)'),
    )
    
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOC_TYPES)
    content = models.TextField()
    is_approved = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    history = models.JSONField(default=list, blank=True) # stores historical content revisions
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_document_type_display()} for Consultation #{self.consultation.id}"

class AIPromptTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    system_prompt = models.TextField()
    user_prompt_template = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} @ {self.timestamp}"

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    action_url = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Notification for {self.user}: {self.title}"

class ConsultationMessage(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='messages')
    sender_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    speaker = models.CharField(max_length=50) # 'Doctor' or 'Patient'
    text = models.TextField()
    audio_file = models.FileField(upload_to='message_audios/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"[{self.speaker} - #{self.consultation.id}]: {self.text[:50]}"

