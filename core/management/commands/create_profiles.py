# core/management/commands/create_profiles.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import UserProfile

class Command(BaseCommand):
    help = "Crée un UserProfile pour chaque utilisateur qui n'en a pas encore"

    def handle(self, *args, **options):
        User = get_user_model()
        count = 0
        for user in User.objects.all():
            if not hasattr(user, "profile"):
                UserProfile.objects.create(user=user)
                count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} profils créés."))
