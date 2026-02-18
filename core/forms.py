# core/forms.py
from allauth.account.forms import SignupForm
from .validators import validate_domain_email
from django import forms

class CustomSignupForm(SignupForm):
    email = forms.EmailField(validators=[validate_domain_email])
