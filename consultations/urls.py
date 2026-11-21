from django.urls import path
from . import views

urlpatterns = [
    path('new/', views.new_consultation, name='new_consultation'),
    path('<int:consultation_id>/transcription/', views.consultation_transcription, name='consultation_transcription'),
    path('<int:consultation_id>/editor/', views.consultation_editor, name='consultation_editor'),
    path('<int:consultation_id>/workspace/', views.consultation_workspace, name='consultation_workspace'),
    path('<int:consultation_id>/room/', views.consultation_room, name='consultation_room'),
    path('<int:consultation_id>/send-message/', views.send_message, name='consultation_send_message'),
    path('<int:consultation_id>/sync/', views.sync_consultation, name='consultation_sync'),
    path('<int:consultation_id>/workspace/process/', views.process_workspace, name='process_workspace'),
    path('<int:consultation_id>/workspace/chat/', views.chat_workspace, name='chat_workspace'),
    path('document/<int:doc_id>/save/', views.save_document, name='save_document'),
    path('document/<int:doc_id>/export/<str:format_type>/', views.export_document, name='export_document'),
    path('list/', views.consultations_list, name='consultations_list'),
    path('patient/<int:patient_id>/timeline/', views.patient_timeline, name='patient_timeline'),
    path('notifications/unread/', views.get_unread_notifications, name='get_unread_notifications'),
    path('notifications/mark-read/', views.mark_notification_read, name='mark_notification_read'),
]


