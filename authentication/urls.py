from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('patient/login/', views.patient_login_view, name='patient_login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('settings/', views.settings_view, name='settings'),
]
