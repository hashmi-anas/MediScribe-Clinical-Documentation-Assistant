from rest_framework.authentication import SessionAuthentication

class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session authentication without CSRF enforcement for internal MediScribe AJAX/API endpoints.
    """
    def enforce_csrf(self, request):
        return
