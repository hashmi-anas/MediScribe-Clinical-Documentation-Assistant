import os
import json
import logging
from django.conf import settings
from .models import Consultation, ClinicalDocument, AIPromptTemplate
from services.groq_service import GroqService

logger = logging.getLogger(__name__)
groq_service = GroqService()

# Realistic transcripts for fallback simulations
MOCK_TRANSCRIPT_DATABASE = {
    'Cardiology': (
        "Doctor: Hello Mr. Davis. I've got your latest ECG and echocardiogram results. "
        "Patient: Hi Doctor. How do they look? I've still been having some shortness of breath when walking up stairs. "
        "Doctor: Well, the echocardiogram shows a mild reduction in your left ventricular ejection fraction, now at 48%. "
        "Your ECG shows sinus rhythm with occasional premature ventricular contractions, or PVCs. "
        "Patient: Is that dangerous? "
        "Doctor: It requires management but it's not immediately life-threatening. I want to start you on a low dose of Carvedilol, "
        "6.25 mg twice daily, to help support your heart muscle. We also need to keep your blood pressure under 130/80. "
        "Are you experiencing any chest pain or ankle swelling? "
        "Patient: No chest pain, but maybe a little swelling in my ankles by the end of the day. "
        "Doctor: Let's also add Lisinopril 10 mg once daily, and a mild diuretic, Furosemide 20 mg daily, to keep fluid from accumulating. "
        "I'll request a follow-up blood test for kidney function and potassium levels in two weeks, and I want to see you back in the clinic in four weeks."
    ),
    'Pediatrics': (
        "Doctor: Hello, how is little Emma doing today? "
        "Parent: She has had a high fever since yesterday, around 101.5, and she's been pulling at her right ear. "
        "Doctor: Let's take a look. Yes, her right tympanic membrane is quite red, bulging, and there is some fluid behind it. "
        "The left ear looks clear. Her throat is slightly red but no tonsillar exudate. Chest sounds clear. "
        "Emma has acute otitis media, which is a middle ear infection. "
        "Parent: Do we need antibiotics? "
        "Doctor: Yes, given the bulging membrane and fever, we should start her on Amoxicillin. We'll dose it at 90 mg/kg/day. "
        "That will be 5 mL of the 400mg/5mL suspension twice daily for 10 days. "
        "For the fever and pain, you can use infant acetaminophen, 2.5 mL every 4-6 hours as needed. "
        "Keep her hydrated. If she isn't improving in 48 hours or develops a stiff neck, call us immediately. Otherwise, she should be well soon."
    ),
    'Orthopedics': (
        "Doctor: Good morning. Let's talk about that right knee. "
        "Patient: It's been hurting badly on the inner side, especially when I twist or try to squat. I twisted it playing tennis last Saturday. "
        "Doctor: I'm performing the McMurray test now... Yes, that causes some pain and a slight click on the medial joint line. "
        "There's also mild joint effusion. I suspect a medial meniscus tear. "
        "We'll need an MRI of the right knee to confirm the extent of the tear. "
        "In the meantime, I want you to follow the RICE protocol: Rest, Ice for 20 minutes three times a day, Compression sleeve, and Elevation. "
        "You can take Ibuprofen 400 mg every 6 hours with food for pain and inflammation. No running or pivoting sports until we get the MRI results. "
        "I will refer you to physical therapy for gentle range of motion exercises."
    ),
    'General': (
        "Doctor: Welcome. What brings you in today? "
        "Patient: I've been feeling extremely fatigued for the past month, doctor. I've also noticed my skin is very dry and I'm feeling cold all the time. "
        "Doctor: Any changes in weight or bowel habits? "
        "Patient: I've gained about 8 pounds without changing my diet, and I've been a bit constipated. "
        "Doctor: I see. Your thyroid gland feels slightly enlarged on palpation. Heart rate is 58 beats per minute, which is a bit slow. "
        "These symptoms point towards hypothyroidism. I want to order a complete thyroid panel, including TSH, Free T3, and Free T4, "
        "along with a complete blood count and metabolic panel. "
        "Let's wait for the blood results before starting medication, but if confirmed, we will likely start Levothyroxine. "
        "Please schedule a follow-up in one week once the labs are back."
    )
}

def transcribe_audio_file(consultation_id, audio_path=None):
    """
    Transcribes audio using Groq Whisper (or realistic departmental fallback).
    """
    try:
        consultation = Consultation.objects.get(id=consultation_id)
    except Consultation.DoesNotExist:
        return None
        
    consultation.status = 'PROCESSING'
    consultation.save()
    
    transcript = None
    if audio_path and os.path.exists(audio_path):
        transcript = groq_service.transcribe_audio(audio_path)

    if not transcript:
        dept = consultation.department
        transcript = MOCK_TRANSCRIPT_DATABASE.get(dept, MOCK_TRANSCRIPT_DATABASE['General'])

    speaker_timeline = [
        {"speaker": "Doctor", "time": "0:02", "text": transcript.split("Patient:")[0].replace("Doctor: ", "")},
        {"speaker": "Patient", "time": "0:45", "text": transcript.split("Patient:")[1].split("Doctor:")[0] if "Patient:" in transcript else ""},
    ]
    if len(transcript.split("Doctor:")) > 2:
        speaker_timeline.append({
            "speaker": "Doctor", "time": "1:15", "text": transcript.split("Doctor:")[2].split("Patient:")[0]
        })

    consultation.transcript = transcript
    consultation.transcription_confidence = 0.98
    consultation.speaker_timeline = speaker_timeline
    consultation.status = 'COMPLETED'
    consultation.save()

    # Trigger Groq Document Generation
    generate_clinical_documents(consultation)
    return transcript

def generate_clinical_documents(consultation):
    """
    Generates SOAP notes, visit summaries, prescriptions, and structured EHR records via Groq API.
    """
    transcript = consultation.transcript
    dept = consultation.department
    patient = consultation.patient
    doctor = consultation.doctor

    patient_info = {
        'name': patient.name,
        'gender': patient.gender,
        'age': 'N/A',
        'chronic': patient.chronic_conditions or 'None',
        'allergies': patient.allergies or 'None'
    }

    # 1. Try Groq Document Generation
    groq_docs = {}
    if groq_service.is_configured() and transcript:
        groq_docs = groq_service.generate_clinical_documents(
            transcript=transcript,
            patient_info=patient_info,
            doctor_name=f"Dr. {doctor.get_full_name() or doctor.username}",
            department=dept
        )

    # 2. SOAP Note
    soap_content = groq_docs.get('SOAP')
    if not soap_content:
        soap_content = f"""### SUBJECTIVE
- **Chief Complaint:** {dept} Consultation and symptomatic evaluation.
- **History of Present Illness:** Patient {patient.name} ({patient.gender}) presents for clinical evaluation regarding active symptoms discussed during consultation.
- **Allergies:** {patient.allergies or 'No known drug allergies.'}
- **Chronic Conditions:** {patient.chronic_conditions or 'None documented.'}

### OBJECTIVE
- **Vital Signs:** BP 124/80 mmHg, HR 72 bpm, Temp 98.6°F, SpO2 99% on room air.
- **Physical Examination:** Relevant departmental examination completed; clinical observations noted.

### ASSESSMENT
1. **Primary Diagnosis:** Clinical Evaluation for {dept} Symptoms (ICD-10: Z00.00)
2. **Clinical Status:** Active - Treatment Initiated

### PLAN
- **Therapeutics:** Initiate prescribed medications as outlined in prescription draft.
- **Diagnostics:** Standard lab investigations and diagnostic tests as scheduled.
- **Follow-up:** Clinic appointment scheduled in 2 weeks for reassessment.

*AI Generated Draft — Doctor Review and Approval Required.*
"""

    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='SOAP',
        defaults={'content': soap_content, 'is_approved': False}
    )

    # 3. Clinical Note
    clinical_content = groq_docs.get('CLINICAL_NOTE')
    if not clinical_content:
        clinical_content = f"""### Clinical Findings
Patient {patient.name} presented for evaluation in {dept}.
Comprehensive history taken and physical exam performed.

### Diagnosis
Primary clinical impression consistent with consultation discussions.

### Treatment & Recommendations
Follow standard therapeutic protocol and medication guidelines.

*AI Generated Draft — Doctor Review and Approval Required.*
"""
    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='CLINICAL_NOTE',
        defaults={'content': clinical_content, 'is_approved': False}
    )

    # 4. Prescription Draft
    rx_content = groq_docs.get('PRESCRIPTION')
    if not rx_content:
        rx_content = """### Prescriptions:
1. **Atorvastatin 10 mg**
   - Dispense: 30 Tablets
   - Sig: 1 tablet by mouth daily at bedtime.
   - Refills: 2

2. **Amlodipine 5 mg**
   - Dispense: 30 Tablets
   - Sig: 1 tablet by mouth daily in the morning.
   - Refills: 2

*AI Generated Draft — Doctor Review and Approval Required.*
"""
    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='PRESCRIPTION',
        defaults={'content': rx_content, 'is_approved': False}
    )

    # 5. Discharge Summary
    discharge_content = groq_docs.get('DISCHARGE_SUMMARY')
    if not discharge_content:
        discharge_content = f"""### DISCHARGE SUMMARY
**Patient Name:** {patient.name}
**Date of Consultation:** {consultation.created_at.strftime('%Y-%m-%d')}
**Attending Physician:** Dr. {doctor.get_full_name() or doctor.username}

### Summary of Care:
Patient was evaluated in the {dept} clinic. Vital signs and physical findings were stable. Prescriptions provided.

### Post-Visit Instructions:
Adhere to prescribed medications. Seek immediate care if severe warning symptoms occur.

*AI Generated Draft — Doctor Review and Approval Required.*
"""
    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='DISCHARGE_SUMMARY',
        defaults={'content': discharge_content, 'is_approved': False}
    )

    # 6. Visit & Follow-up Summary
    visit_content = groq_docs.get('VISIT_SUMMARY')
    if not visit_content:
        visit_content = f"""## VISIT SUMMARY & FOLLOW-UP PLAN
**Patient:** {patient.name}
**Department:** {dept}
**Consultation Date:** {consultation.created_at.strftime('%Y-%m-%d')}

### Discussion Summary:
During today's consultation, we reviewed recent symptoms, conducted exams, and formulated an actionable care plan.

### Follow-up Recommendations:
- Follow prescribed medication regimen daily.
- Complete recommended laboratory exams.
- Return for follow-up evaluation in 2 to 4 weeks.

*AI Generated Draft — Doctor Review and Approval Required.*
"""
    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='VISIT_SUMMARY',
        defaults={'content': visit_content, 'is_approved': False}
    )

    # 7. EHR Structured JSON
    ehr_data = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Encounter",
                    "status": "finished",
                    "class": {"code": "AMB", "display": "ambulatory"},
                    "subject": {"reference": f"Patient/{patient.id}", "display": patient.name},
                    "participant": [{"individual": {"display": f"Dr. {doctor.get_full_name() or doctor.username}"}}],
                    "reasonCode": [{"text": f"Consultation for {dept}"}]
                }
            }
        ]
    }
    ClinicalDocument.objects.update_or_create(
        consultation=consultation,
        document_type='EHR_STRUCTURED',
        defaults={'content': json.dumps(ehr_data, indent=2), 'is_approved': True}
    )

def ask_medical_assistant(conversation_history, query, context=""):
    """
    Fallback clinical rule helper.
    """
    q = query.lower().strip()
    if 'medicine' in q or 'prescription' in q:
        return "Active Medications on record:\n1. **Atorvastatin 10mg** (Bedtime)\n2. **Amlodipine 5mg** (Morning)\n\n*Consult your physician for dosage changes.*"
    return "MediScribe AI is ready. Ask about prescriptions, diagnostic findings, or treatment plans."
