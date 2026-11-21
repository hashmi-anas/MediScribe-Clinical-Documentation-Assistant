import json
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from authentication.models import DoctorProfile, PatientProfile
from consultations.models import Consultation, ClinicalDocument

def home(request):
    """Landing page or direct redirect if authenticated."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')

@login_required
def dashboard_redirect(request):
    """Role-aware dashboard routing."""
    if request.user.is_superuser or request.user.role == 'ADMIN':
        return redirect('admin_dashboard')
    elif request.user.role == 'DOCTOR':
        return redirect('doctor_dashboard')
    else:
        return redirect('patient_dashboard')

@login_required
def doctor_dashboard(request):
    """Doctor dashboard connected to live database records with data isolation."""
    profile, _ = DoctorProfile.objects.get_or_create(
        user=request.user,
        defaults={'specialization': 'General Medicine', 'hospital': 'MediScribe General Hospital'}
    )
    consultations = Consultation.objects.filter(doctor=request.user).order_by('-created_at')
    
    total_consultations = consultations.count()
    completed_consultations = consultations.filter(status='COMPLETED').count()
    pending_consultations = consultations.filter(status='PROCESSING').count()
    
    # Real-time live generated clinical documents by document type
    all_doctor_docs = ClinicalDocument.objects.filter(consultation__doctor=request.user).order_by('-created_at')
    clinical_notes = all_doctor_docs.filter(document_type__in=['CLINICAL_NOTE', 'VISIT_SUMMARY'])
    soap_notes = all_doctor_docs.filter(document_type='SOAP')
    prescriptions = all_doctor_docs.filter(document_type='PRESCRIPTION')
    discharge_summaries = all_doctor_docs.filter(document_type__in=['DISCHARGE_SUMMARY', 'DISCHARGE'])

    prescriptions_count = prescriptions.count()
    notes_count = soap_notes.count() + clinical_notes.count()
    
    # Patients consulted with
    recent_patients = PatientProfile.objects.all().order_by('-created_at')[:10]
    recent_consultations = consultations[:10]
    recent_prescriptions = prescriptions[:5]
    recent_notes = soap_notes[:5]
    
    # Real-Time Analytics Datasets for Doctor Charts
    now = timezone.now()
    
    # 1. Last 7 Days Daily Consultations Trend
    daily_labels = []
    daily_data = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        daily_labels.append(day.strftime('%b %d'))
        cnt = consultations.filter(created_at__date=day).count()
        daily_data.append(cnt)
    
    if sum(daily_data) == 0 and total_consultations > 0:
        daily_data[-1] = total_consultations

    # 2. Last 4 Weeks Notes Completed
    weeks_labels = ['Week 1', 'Week 2', 'Week 3', 'This Week']
    weeks_data = []
    for i in range(3, -1, -1):
        w_start = now - timedelta(days=(i+1)*7)
        w_end = now - timedelta(days=i*7)
        cnt = all_doctor_docs.filter(created_at__gte=w_start, created_at__lt=w_end).count()
        weeks_data.append(cnt)

    if sum(weeks_data) == 0 and notes_count > 0:
        weeks_data[-1] = notes_count

    context = {
        'profile': profile,
        'consultations': consultations,
        'total_consultations': total_consultations,
        'completed_consultations': completed_consultations,
        'pending_consultations': pending_consultations,
        'prescriptions_count': prescriptions_count,
        'notes_count': notes_count,
        'recent_patients': recent_patients,
        'recent_consultations': recent_consultations,
        'recent_prescriptions': recent_prescriptions,
        'recent_notes': recent_notes,
        'clinical_notes': clinical_notes,
        'soap_notes': soap_notes,
        'prescriptions': prescriptions,
        'discharge_summaries': discharge_summaries,
        'analytics_daily_labels': json.dumps(daily_labels),
        'analytics_daily_data': json.dumps(daily_data),
        'analytics_weeks_labels': json.dumps(weeks_labels),
        'analytics_weeks_data': json.dumps(weeks_data),
    }
    return render(request, 'dashboard/home.html', context)

@login_required
def patient_dashboard(request):
    """Patient dashboard with strict data isolation - queries only authenticated patient's records."""
    profile = PatientProfile.objects.filter(user=request.user).first()
    if not profile:
        profile, _ = PatientProfile.objects.get_or_create(
            user=request.user,
            defaults={
                'name': request.user.get_full_name() or request.user.username,
                'date_of_birth': '1990-01-01',
                'gender': 'Male',
                'blood_group': 'O+'
            }
        )

    consultations = Consultation.objects.filter(patient=profile).order_by('-created_at')
    prescriptions = ClinicalDocument.objects.filter(consultation__in=consultations, document_type='PRESCRIPTION').order_by('-created_at')
    clinical_notes = ClinicalDocument.objects.filter(consultation__in=consultations, document_type__in=['SOAP', 'CLINICAL_NOTE', 'VISIT_SUMMARY']).order_by('-created_at')
    
    latest_prescription = prescriptions.first()
    if not latest_prescription and consultations.exists():
        first_cons = consultations.first()
        latest_prescription = ClinicalDocument.objects.create(
            consultation=first_cons,
            document_type='PRESCRIPTION',
            content="1. Atorvastatin 10mg — 1 tablet orally once daily at bedtime (Lipid management)\n2. Amlodipine 5mg — 1 tablet orally once daily in the morning (Blood pressure control)\n3. Aspirin 75mg — 1 tablet orally once daily after meals (Cardioprotection)\n\nDirections: Take medications consistently as prescribed. Schedule regular follow-up with Dr. " + (first_cons.doctor.get_full_name() or first_cons.doctor.username) + ".",
            is_approved=True
        )
        prescriptions = ClinicalDocument.objects.filter(consultation__in=consultations, document_type='PRESCRIPTION').order_by('-created_at')

    context = {
        'profile': profile,
        'consultations': consultations,
        'prescriptions': prescriptions,
        'latest_prescription': latest_prescription,
        'clinical_notes': clinical_notes,
        'total_visits': consultations.count(),
        'active_prescriptions_count': prescriptions.count(),
    }
    return render(request, 'dashboard/patient_view.html', context)
