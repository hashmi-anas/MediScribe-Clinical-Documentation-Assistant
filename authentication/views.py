from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CustomUser, DoctorProfile, PatientProfile
from consultations.models import AuditLog

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role', 'DOCTOR') # DOCTOR or ADMIN
        remember_me = request.POST.get('remember_me') == 'on'
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # If user is a superuser / staff, allow login seamlessly and sync role if Admin
            if user.is_superuser or user.is_staff or user.username.lower() == 'admin':
                if role == 'ADMIN' and user.role != 'ADMIN':
                    user.role = 'ADMIN'
                    user.save(update_fields=['role'])
                login(request, user)
                if not remember_me:
                    request.session.set_expiry(0)
                
                AuditLog.objects.create(
                    user=user,
                    action=f"Logged in successfully as {user.role}"
                )
                return redirect('admin_dashboard' if user.role == 'ADMIN' else 'doctor_dashboard')
            
            # Standard doctor or admin login check
            if user.role == role:
                login(request, user)
                if not remember_me:
                    request.session.set_expiry(0)
                
                AuditLog.objects.create(
                    user=user,
                    action=f"Logged in successfully as {role}"
                )
                return redirect('dashboard')
            elif user.role == 'PATIENT':
                messages.error(request, "Patient account detected. Please use the Patient Sign In portal.")
            else:
                messages.error(request, f"Access Denied: Account is registered as {user.role}, not {role}.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'auth/login.html')

def patient_login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me') == 'on'
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.role == 'PATIENT' or user.is_superuser:
                login(request, user)
                if not remember_me:
                    request.session.set_expiry(0)
                
                AuditLog.objects.create(
                    user=user,
                    action="Logged in successfully as PATIENT"
                )
                return redirect('patient_dashboard')
            else:
                messages.error(request, f"Access Denied: Account is registered as {user.role}. Please use Doctor/Admin Sign In.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'auth/patient_login.html')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        role = 'PATIENT' # Registration is exclusively for Patients now
        
        gender = request.POST.get('gender', 'Male')
        date_of_birth = request.POST.get('date_of_birth', '1990-01-01')
        blood_group = request.POST.get('blood_group', 'O+')
        
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, 'auth/register.html')
            
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role
        )
        
        PatientProfile.objects.create(
            user=user,
            name=f"{first_name} {last_name}",
            date_of_birth=date_of_birth,
            gender=gender,
            blood_group=blood_group
        )
            
        login(request, user)
        AuditLog.objects.create(
            user=user,
            action=f"Patient registered account and logged in: {username}"
        )
        return redirect('dashboard')
        
    return render(request, 'auth/register.html')

def logout_view(request):
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action="Logged out"
        )
    logout(request)
    return redirect('home')

@login_required
def profile_view(request):
    profile, created = DoctorProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        request.user.phone = request.POST.get('phone', request.user.phone)
        request.user.save()
        
        profile.specialization = request.POST.get('specialization', profile.specialization)
        profile.experience_years = int(request.POST.get('experience_years', profile.experience_years))
        profile.hospital = request.POST.get('hospital', profile.hospital)
        profile.preferred_language = request.POST.get('preferred_language', profile.preferred_language)
        profile.save()
        
        messages.success(request, "Profile updated successfully.")
        
    return render(request, 'dashboard/profile.html', {'profile': profile})

@login_required
def settings_view(request):
    profile, created = DoctorProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        profile.theme_preference = request.POST.get('theme_preference', profile.theme_preference)
        profile.speech_model = request.POST.get('speech_model', profile.speech_model)
        profile.llm_model = request.POST.get('llm_model', profile.llm_model)
        profile.api_key_openai = request.POST.get('api_key_openai', profile.api_key_openai)
        profile.api_key_gemini = request.POST.get('api_key_gemini', profile.api_key_gemini)
        profile.save()
        messages.success(request, "Settings updated successfully.")
        
    return render(request, 'dashboard/settings.html', {'profile': profile})
