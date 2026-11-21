from django.urls import path
from . import views

urlpatterns = [
    # Primary Chatbot Endpoints
    path('chatbot/message/', views.chatbot_message_endpoint, name='api_chatbot_message'),
    path('chatbot/', views.chatbot_message_endpoint, name='api_chatbot_root'),
    path('ai/agent/', views.ai_agent_endpoint, name='api_ai_agent'),
    path('assistant/', views.assistant_chat, name='api_assistant'),
    
    # Architecture Specific REST Endpoints
    path('users/', views.users_list_api, name='api_users'),
    path('patients/', views.patients_list_api, name='api_patients'),
    path('doctors/', views.doctors_list_api, name='api_doctors'),
    path('consultations/', views.consultations_list_api, name='api_consultations'),
    path('speech/transcribe/', views.speech_transcribe_api, name='api_speech_transcribe'),
    path('nlp/extract/', views.nlp_extract_api, name='api_nlp_extract'),
    path('llm/generate/', views.llm_generate_api, name='api_llm_generate'),
    path('clinical-notes/', views.clinical_notes_api, name='api_clinical_notes'),
    path('prescriptions/', views.prescriptions_api, name='api_prescriptions'),
    path('reports/', views.reports_api, name='api_reports'),
    path('followups/', views.followups_api, name='api_followups'),
    path('audit/', views.audit_logs_api, name='api_audit'),
    path('system/status/', views.system_status_api, name='api_system_status'),
    path('system/config/', views.system_status_api, name='api_system_config'),
    
    # Analytics & Dashboard endpoints
    path('analytics/', views.analytics_data, name='api_analytics'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/prompt/<int:prompt_id>/update/', views.update_prompt, name='update_prompt'),

    # AI Shortcut Endpoints
    path('ai/chat/', views.ai_chat_endpoint, name='api_ai_chat'),
    path('ai/patient-summary/', views.ai_patient_summary, name='api_ai_patient_summary'),
    path('ai/doctor-summary/', views.ai_doctor_summary, name='api_ai_doctor_summary'),
    path('ai/report-summary/', views.ai_report_summary, name='api_ai_report_summary'),
    path('ai/prescription-explainer/', views.ai_prescription_explainer, name='api_ai_prescription_explainer'),
    path('ai/dashboard-insights/', views.ai_dashboard_insights, name='api_ai_dashboard_insights'),
]
