import os
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from authentication.models import PatientProfile, DoctorProfile, CustomUser
from .models import Consultation, ClinicalDocument, AIPromptTemplate, AuditLog, ConsultationMessage, Notification
from .ai_engine import transcribe_audio_file, generate_clinical_documents
from services.groq_service import GroqService
from services.ai_agent import AIAgent
from services.permissions import PermissionValidator

groq_service = GroqService()
ai_agent = AIAgent()

@login_required
def new_consultation(request):
    """Start a new doctor-patient consultation session initiated by either Doctor or Patient."""
    is_patient = (request.user.role == 'PATIENT')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if is_patient or action == 'patient_start':
            # Patient initiating consultation
            doctor_profile_id = request.POST.get('doctor_id')
            doctor_profile = DoctorProfile.objects.filter(id=doctor_profile_id).first()
            if not doctor_profile:
                doctor_user = CustomUser.objects.filter(role='DOCTOR').first()
                if not doctor_user:
                    doctor_user = request.user
            else:
                doctor_user = doctor_profile.user

            patient_profile = PatientProfile.objects.filter(user=request.user).first()
            if not patient_profile:
                patient_profile, _ = PatientProfile.objects.get_or_create(
                    user=request.user,
                    defaults={
                        'name': request.user.get_full_name() or request.user.username,
                        'date_of_birth': '1990-01-01',
                        'gender': 'Male',
                        'blood_group': 'O+'
                    }
                )

            department = request.POST.get('department') or getattr(doctor_profile, 'specialization', 'General Medicine')
            visit_type = request.POST.get('visit_type') or 'Live Audio / Chat Consultation'
            language = request.POST.get('language', 'English')
            specialty = getattr(doctor_profile, 'specialization', 'General Practice')
            reason = request.POST.get('reason', '').strip()

            consultation = Consultation.objects.create(
                doctor=doctor_user,
                patient=patient_profile,
                department=department,
                visit_type=visit_type,
                language=language,
                specialty=specialty,
                status='RECORDING',
                transcript=f"Patient: Hello Doctor, I am starting our consultation. {reason}" if reason else ""
            )

            if reason:
                ConsultationMessage.objects.create(
                    consultation=consultation,
                    sender_user=request.user,
                    speaker='Patient',
                    text=f"Reason for consultation: {reason}"
                )

            # Send real-time notification alert to Doctor
            Notification.objects.create(
                user=doctor_user,
                title="New Patient Consultation Started",
                message=f"Patient {patient_profile.name} has initiated Consultation #{consultation.id} ({department}).",
                action_url=f"/consultations/{consultation.id}/workspace/"
            )

            AuditLog.objects.create(
                user=request.user,
                action=f"Patient {patient_profile.name} initiated Consultation #{consultation.id} with Dr. {doctor_user.username}"
            )

            return redirect('consultation_room', consultation_id=consultation.id)

        elif action == 'create_patient':
            name = request.POST.get('name')
            gender = request.POST.get('gender', 'Male')
            dob = request.POST.get('date_of_birth', '1990-01-01')
            blood_group = request.POST.get('blood_group', 'O+')
            allergies = request.POST.get('allergies', '')
            chronic = request.POST.get('chronic_conditions', '')
            
            patient = PatientProfile.objects.create(
                name=name,
                gender=gender,
                date_of_birth=dob,
                blood_group=blood_group,
                allergies=allergies,
                chronic_conditions=chronic
            )
            AuditLog.objects.create(
                user=request.user,
                action=f"Created new patient profile: {name}"
            )
            department = request.POST.get('department', 'General Medicine')
            visit_type = request.POST.get('visit_type', 'Outpatient Consultation')
            language = request.POST.get('language', 'English')
            specialty = request.POST.get('specialty', 'General Practice')
            
            consultation = Consultation.objects.create(
                doctor=request.user,
                patient=patient,
                department=department,
                visit_type=visit_type,
                language=language,
                specialty=specialty,
                status='RECORDING'
            )
            
            if patient.user:
                Notification.objects.create(
                    user=patient.user,
                    title="Live Consultation Started",
                    message=f"Dr. {request.user.get_full_name() or request.user.username} has started Consultation #{consultation.id} with you.",
                    action_url=f"/consultations/{consultation.id}/room/"
                )

            AuditLog.objects.create(
                user=request.user,
                action=f"Doctor {request.user.username} started Consultation #{consultation.id} for {patient.name}"
            )
            return redirect('consultation_workspace', consultation_id=consultation.id)

        else:
            patient_id = request.POST.get('patient_id')
            department = request.POST.get('department', 'Cardiology')
            visit_type = request.POST.get('visit_type', 'Outpatient Consultation')
            language = request.POST.get('language', 'English')
            specialty = request.POST.get('specialty', 'General Practice')
            patient = get_object_or_404(PatientProfile, id=patient_id)
        
            consultation = Consultation.objects.create(
                doctor=request.user,
                patient=patient,
                department=department,
                visit_type=visit_type,
                language=language,
                specialty=specialty,
                status='RECORDING'
            )
            
            if patient.user:
                Notification.objects.create(
                    user=patient.user,
                    title="Doctor Started Consultation",
                    message=f"Dr. {request.user.get_full_name() or request.user.username} has started Consultation #{consultation.id} with you ({department}).",
                    action_url=f"/consultations/{consultation.id}/room/"
                )

            AuditLog.objects.create(
                user=request.user,
                action=f"Doctor {request.user.username} started Consultation #{consultation.id} for {patient.name}"
            )
            
            return redirect('consultation_workspace', consultation_id=consultation.id)
        
    patients = PatientProfile.objects.all().order_by('-created_at')
    doctors = DoctorProfile.objects.select_related('user').all()
    departments = ['Cardiology', 'Pediatrics', 'Orthopedics', 'General Medicine', 'Neurology', 'Dermatology']
    languages = ['English', 'Spanish', 'French', 'German', 'Mandarin']
    
    context = {
        'patients': patients,
        'doctors': doctors,
        'departments': departments,
        'languages': languages,
        'is_patient': is_patient,
    }
    return render(request, 'consultations/new.html', context)

@login_required
def consultation_room(request, consultation_id):
    """
    Dedicated interactive live consultation room for Patient and Doctor with real-time synchronized
    voice STT, instant messaging, status indicators, and live clinical document delivery.
    """
    allowed, err_or_obj = PermissionValidator.can_access_consultation(request.user, consultation_id)
    if not allowed:
        return HttpResponse(f"Access Denied: {err_or_obj}", status=403)
        
    consultation = err_or_obj
    doctor_profile = DoctorProfile.objects.filter(user=consultation.doctor).first()
    messages_list = consultation.messages.all().order_by('created_at')
    documents = consultation.documents.all()
    
    context = {
        'consultation': consultation,
        'doctor_profile': doctor_profile,
        'patient': consultation.patient,
        'messages': messages_list,
        'documents': documents,
        'is_patient': (request.user.role == 'PATIENT'),
    }
    return render(request, 'consultations/room.html', context)

@login_required
def send_message(request, consultation_id):
    """
    Endpoint to send and broadcast a live dialogue line or audio transcription
    from either Doctor or Patient into the synchronized consultation conversation.
    """
    if request.method == 'POST':
        allowed, err_or_obj = PermissionValidator.can_access_consultation(request.user, consultation_id)
        if not allowed:
            return JsonResponse({'status': 'denied', 'message': str(err_or_obj)}, status=403)

        consultation = err_or_obj
        default_speaker = 'Patient' if request.user.role == 'PATIENT' else 'Doctor'
        speaker = request.POST.get('speaker', default_speaker)
        text = request.POST.get('text', '').strip()
        audio_file = request.FILES.get('audio_file')

        if not text and audio_file:
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                    for chunk in audio_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name
                text = groq_service.transcribe_audio(tmp_path) or ""
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception as e:
                pass

        if not text:
            return JsonResponse({'status': 'failed', 'message': 'Message text is required'}, status=400)

        msg = ConsultationMessage.objects.create(
            consultation=consultation,
            sender_user=request.user,
            speaker=speaker,
            text=text,
            audio_file=audio_file
        )

        formatted_line = f"{speaker}: {text}"
        if consultation.transcript and consultation.transcript.strip():
            consultation.transcript = f"{consultation.transcript.strip()}\n\n{formatted_line}"
        else:
            consultation.transcript = formatted_line
        consultation.save(update_fields=['transcript', 'updated_at'])

        # Create alert notification for the counter-party
        if speaker == 'Doctor' and consultation.patient.user:
            Notification.objects.create(
                user=consultation.patient.user,
                title=f"New Message from Dr. {consultation.doctor.get_full_name() or consultation.doctor.username}",
                message=text[:100],
                action_url=f"/consultations/{consultation.id}/room/"
            )
        elif speaker == 'Patient':
            Notification.objects.create(
                user=consultation.doctor,
                title=f"New Message from {consultation.patient.name}",
                message=text[:100],
                action_url=f"/consultations/{consultation.id}/workspace/"
            )

        return JsonResponse({
            'status': 'success',
            'message': {
                'id': msg.id,
                'speaker': msg.speaker,
                'text': msg.text,
                'timestamp': msg.created_at.strftime('%H:%M:%S'),
                'is_self': True
            },
            'transcript': consultation.transcript
        })

    return JsonResponse({'status': 'failed', 'message': 'Invalid request method'}, status=400)

@login_required
def get_unread_notifications(request):
    """API endpoint to poll unread notifications for current authenticated user."""
    unread = Notification.objects.filter(user=request.user, is_read=False).order_by('-timestamp')[:15]
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    data = [{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'action_url': n.action_url or '',
        'time': n.timestamp.strftime('%H:%M'),
        'timestamp': n.timestamp.isoformat()
    } for n in unread]
    return JsonResponse({'status': 'success', 'count': count, 'notifications': data})

@login_required
def mark_notification_read(request):
    """API endpoint to mark notifications as read."""
    if request.method == 'POST':
        notif_id = request.POST.get('notification_id')
        if notif_id:
            Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'failed'}, status=400)


@login_required
def sync_consultation(request, consultation_id):
    """
    Real-time synchronization polling endpoint. Returns all new messages since `last_id`,
    live consultation status, latest full transcript, and updated clinical documents.
    """
    allowed, err_or_obj = PermissionValidator.can_access_consultation(request.user, consultation_id)
    if not allowed:
        return JsonResponse({'status': 'denied', 'message': str(err_or_obj)}, status=403)

    consultation = err_or_obj
    last_id = int(request.GET.get('last_id', 0))

    new_messages = consultation.messages.filter(id__gt=last_id).order_by('created_at')
    msgs_data = [{
        'id': m.id,
        'speaker': m.speaker,
        'text': m.text,
        'timestamp': m.created_at.strftime('%H:%M:%S'),
        'is_self': (m.sender_user_id == request.user.id)
    } for m in new_messages]

    docs_data = {}
    for doc in consultation.documents.all():
        docs_data[doc.document_type] = {
            'id': doc.id,
            'content': doc.content,
            'is_approved': doc.is_approved
        }

    return JsonResponse({
        'status': consultation.status,
        'messages': msgs_data,
        'transcript': consultation.transcript or '',
        'documents': docs_data,
        'consultation_id': consultation.id
    })

@login_required
def consultation_transcription(request, consultation_id):
    """Transcription dedicated view / redirect to live workspace."""
    consultation = get_object_or_404(Consultation, id=consultation_id)
    if consultation.doctor != request.user and request.user.role != 'ADMIN':
        return HttpResponse("Access Denied", status=403)
    
    if request.method == 'POST':
        transcribe_audio_file(consultation.id)
        return JsonResponse({'status': 'success', 'redirect_url': f'/consultations/{consultation.id}/workspace/'})
        
    return render(request, 'consultations/transcription.html', {'consultation': consultation})

@login_required
def consultation_editor(request, consultation_id):
    """Document editor dedicated view."""
    consultation = get_object_or_404(Consultation, id=consultation_id)
    if consultation.doctor != request.user and request.user.role != 'ADMIN':
        return HttpResponse("Access Denied", status=403)
    
    documents = consultation.documents.all()
    if not documents.exists():
        generate_clinical_documents(consultation)
        documents = consultation.documents.all()
        
    active_doc_type = request.GET.get('type', 'SOAP')
    active_doc = documents.filter(document_type=active_doc_type).first() or documents.first()
    
    context = {
        'consultation': consultation,
        'documents': documents,
        'active_doc': active_doc,
        'active_doc_type': active_doc_type,
    }
    return render(request, 'consultations/editor.html', context)

@login_required
def consultation_workspace(request, consultation_id):
    """Multi-column live clinical workspace for recording, transcription, NLP extraction, document review & AI chatbot."""
    allowed, err_or_obj = PermissionValidator.can_access_consultation(request.user, consultation_id)
    if not allowed:
        return HttpResponse("Access Denied: You are not authorized for this session.", status=403)

    consultation = err_or_obj
    patient = consultation.patient
    recent_consultations = Consultation.objects.filter(patient=patient).exclude(id=consultation.id).order_by('-created_at')[:5]
    documents = consultation.documents.all()
    messages_list = consultation.messages.all().order_by('created_at')
    
    context = {
        'consultation': consultation,
        'patient': patient,
        'recent_consultations': recent_consultations,
        'documents': documents,
        'messages': messages_list,
    }
    return render(request, 'consultations/workspace.html', context)



@login_required
def process_workspace(request, consultation_id):
    """
    Processes audio recording / transcript through Groq STT & NLP & LLM pipelines.
    Generates draft SOAP, Clinical Note, Prescription, Discharge Summary, and Visit Summary.
    """
    if request.method == 'POST':
        consultation = get_object_or_404(Consultation, id=consultation_id)
        if consultation.doctor != request.user and request.user.role != 'ADMIN':
            return JsonResponse({'status': 'denied', 'message': 'Unauthorized'}, status=403)

        transcript = request.POST.get('transcript', '')
        audio_file = request.FILES.get('audio_file')

        if audio_file:
            consultation.raw_audio = audio_file
            consultation.save()
            try:
                audio_path = consultation.raw_audio.path
                stt_transcript = groq_service.transcribe_audio(audio_path)
                if stt_transcript:
                    if transcript and len(transcript.strip()) > 10:
                        transcript = f"{transcript.strip()}\n\n[Voice Audio Transcription]:\n{stt_transcript}"
                    else:
                        transcript = stt_transcript
            except Exception as e:
                pass

        if not transcript or not transcript.strip():
            transcript = "Doctor: Routine consultation conducted. Vital signs evaluated. Patient advised on treatment plan."

        consultation.transcript = transcript
        consultation.status = 'COMPLETED'
        consultation.save()

        # Generate Groq Clinical Documentation
        generate_clinical_documents(consultation)

        AuditLog.objects.create(
            user=request.user,
            action=f"Processed Consultation #{consultation.id} with Groq AI Documentation Engine"
        )

        docs_data = {}
        for doc in consultation.documents.all():
            docs_data[doc.document_type] = {
                'id': doc.id,
                'content': doc.content,
                'is_approved': doc.is_approved
            }
            
        return JsonResponse({
            'status': 'success',
            'transcript': consultation.transcript,
            'documents': docs_data
        })
    return JsonResponse({'status': 'failed'}, status=400)

@login_required
def save_document(request, doc_id):
    """Save doctor revisions or approve clinical document."""
    if request.method == 'POST':
        doc = get_object_or_404(ClinicalDocument, id=doc_id)
        if doc.consultation.doctor != request.user and request.user.role != 'ADMIN':
            return JsonResponse({'status': 'denied'}, status=403)

        content = request.POST.get('content')
        approve = request.POST.get('approve') == 'true'
        
        # Save historical revision
        history_item = {
            'version': doc.version,
            'content': doc.content,
            'updated_by': request.user.username,
            'timestamp': doc.updated_at.isoformat() if doc.updated_at else ''
        }
        doc.history.append(history_item)
        
        doc.content = content
        doc.is_approved = approve
        doc.version += 1
        doc.save()
        
        action_verb = "Approved & Finalized" if approve else "Saved Revision for"
        AuditLog.objects.create(
            user=request.user,
            action=f"{action_verb} Clinical Document #{doc.id} ({doc.document_type}) v{doc.version}"
        )
        
        return JsonResponse({'status': 'success', 'version': doc.version, 'is_approved': doc.is_approved})
    return JsonResponse({'status': 'failed'}, status=400)

@login_required
def export_document(request, doc_id, format_type):
    """Exports clinical document in PDF (printable layout), FHIR/HL7 JSON, or TXT format."""
    doc = get_object_or_404(ClinicalDocument, id=doc_id)
    # Check access permission via PermissionValidator
    allowed, err_or_obj = PermissionValidator.can_access_document(request.user, doc.id)
    if not allowed:
        return HttpResponse(f"Access Denied: {err_or_obj}", status=403)
    
    filename = f"MediScribe_{doc.document_type}_{doc.consultation.patient.name.replace(' ', '_')}"
    
    if format_type == 'txt':
        response = HttpResponse(doc.content, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}.txt"'
        return response
        
    elif format_type == 'json':
        response = HttpResponse(doc.content, content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
        return response
        
    elif format_type == 'pdf':
        status_tag = '<span style="color: #078A83; font-weight: bold;">[ APPROVED & FINALIZED ]</span>' if doc.is_approved else '<span style="color: #FF6B21; font-weight: bold;">[ AI GENERATED DRAFT — CLINICIAN REVIEW REQUIRED ]</span>'
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>{doc.get_document_type_display()} — {doc.consultation.patient.name}</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; color: #07152D; line-height: 1.6; background-color: #F4FAFA; }}
                .header {{ border-bottom: 2px solid #67DDE0; padding-bottom: 15px; margin-bottom: 25px; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #07152D; }}
                .meta-box {{ background: #FFFFFF; border: 1px solid #67DDE0; border-radius: 8px; padding: 15px; margin-bottom: 25px; }}
                .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px; color: #07152D; }}
                .content {{ white-space: pre-wrap; font-size: 14px; background: #FFFFFF; padding: 20px; border: 1px solid #67DDE0; border-radius: 8px; color: #07152D; }}
                .footer {{ margin-top: 40px; border-top: 1px solid #67DDE0; padding-top: 15px; font-size: 11px; color: #07152D; opacity: 0.8; text-align: center; }}
            </style>
        </head>
        <body onload="window.print()">
            <div class="header">
                <div class="logo">Medi<span style="color: #078A83;">Scribe</span> Healthcare Documentation</div>
                <div style="font-size: 12px; color: #07152D; opacity: 0.8;">Automated Clinical Documentation System</div>
            </div>
            <h2 style="color: #07152D;">{doc.get_document_type_display()} &mdash; {status_tag}</h2>
            <div class="meta-box">
                <div class="meta-grid">
                    <div><strong>Patient Name:</strong> {doc.consultation.patient.name}</div>
                    <div><strong>Date of Visit:</strong> {doc.consultation.created_at.strftime('%Y-%m-%d %H:%M')}</div>
                    <div><strong>Attending Physician:</strong> Dr. {doc.consultation.doctor.get_full_name() or doc.consultation.doctor.username}</div>
                    <div><strong>Department:</strong> {doc.consultation.department} ({doc.consultation.specialty})</div>
                    <div><strong>Document Version:</strong> v{doc.version}</div>
                    <div><strong>Approval Status:</strong> {'Approved' if doc.is_approved else 'Draft Pending'}</div>
                </div>
            </div>
            <div class="content">{doc.content}</div>
            <div class="footer">
                MediScribe AI Clinical Documentation Platform • Confidential Medical Record • Document #{doc.id}
            </div>
        </body>
        </html>"""
        return HttpResponse(html_content)
        
    return HttpResponse("Unsupported export format", status=400)

@login_required
def chat_workspace(request, consultation_id):
    """Context-aware AI Copilot in the Consultation Workspace."""
    if request.method == 'POST':
        consultation = get_object_or_404(Consultation, id=consultation_id)
        query = request.POST.get('query', '')
        history_json = request.POST.get('history', '[]')
        
        context = {
            'consultation_id': consultation.id,
            'patient_id': consultation.patient.id,
            'patient_name': consultation.patient.name,
            'department': consultation.department
        }
        
        result = ai_agent.process_request(
            user=request.user,
            query=query,
            conversation_history=json.loads(history_json),
            current_context=context
        )
        
        return JsonResponse({
            'status': 'success',
            'reply': result.get('message', ''),
            'data': result.get('data'),
            'ui_action': result.get('ui_action')
        })
    return JsonResponse({'status': 'failed'}, status=400)

@login_required
def consultations_list(request):
    consultations = Consultation.objects.filter(doctor=request.user).order_by('-created_at')
    return render(request, 'consultations/list.html', {'consultations': consultations})

@login_required
def patient_timeline(request, patient_id):
    patient = get_object_or_404(PatientProfile, id=patient_id)
    consultations = Consultation.objects.filter(patient=patient).order_by('-created_at')
    return render(request, 'dashboard/patient_timeline.html', {'patient': patient, 'consultations': consultations})
