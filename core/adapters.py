from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.shortcuts import resolve_url

class CoreAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)

    def get_email_verification_redirect_url(self, email_address):
        return resolve_url("account_reset_password_done")

    def is_login_by_code_required(self, *args, **kwargs): return False
    def is_login_by_code_enabled(self, *args, **kwargs):  return False

from allauth.account.adapter import DefaultAccountAdapter
from allauth.utils import generate_unique_username

class NoUsernameAccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        # Fallback "safe" si jamais save_user n'est pas appelé
        suggestions = []
        email = getattr(user, "email", "") or ""
        if email:
            suggestions.append(email.split("@", 1)[0])
        suggestions.append("user")
        user.username = generate_unique_username(suggestions)

    def save_user(self, request, user, form, commit=True):
        # Laisse allauth créer l'utilisateur (pose email, etc.)
        user = super().save_user(request, user, form, commit=False)

        # Garantit un username généré à partir des données validées
        if not getattr(user, "username", ""):
            email = (form.cleaned_data.get("email") or "").strip()
            base = email.split("@", 1)[0] if "@" in email else email
            user.username = generate_unique_username([base, "user"])

        if commit:
            user.save()
        return user
