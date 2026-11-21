from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('DOCTOR', 'Doctor'),
        ('ADMIN', 'Administrator'),
        ('PATIENT', 'Patient'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='DOCTOR')
    phone = models.CharField(max_length=15, blank=True, null=True)

    def is_doctor(self):
        return self.role == 'DOCTOR'

    def is_admin_user(self):
        return self.role == 'ADMIN'

class DoctorProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.CharField(max_length=100, default='General Medicine')
    experience_years = models.IntegerField(default=5)
    hospital = models.CharField(max_length=150, default='MediScribe General Hospital')
    preferred_language = models.CharField(max_length=50, default='English')
    api_key_openai = models.CharField(max_length=255, blank=True, null=True)
    api_key_gemini = models.CharField(max_length=255, blank=True, null=True)
    theme_preference = models.CharField(max_length=10, default='dark') # dark or light
    speech_model = models.CharField(max_length=50, default='whisper-1')
    llm_model = models.CharField(max_length=50, default='gemini-1.5-flash')
    
    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username} ({self.specialization})"

class PatientProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='patient_profile', blank=True, null=True)
    name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=(('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')))
    blood_group = models.CharField(max_length=5, blank=True, null=True)
    allergies = models.TextField(blank=True, null=True)
    chronic_conditions = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
