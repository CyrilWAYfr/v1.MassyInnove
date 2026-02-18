# logement/admin.py

from django.contrib import admin
from .models import Domaine, DomaineUser

@admin.register(Domaine)
class DomaineAdmin(admin.ModelAdmin):
    list_display = ("libelle", "ordre")
    ordering = ("ordre", "libelle")
    search_fields = ("libelle",)

@admin.register(DomaineUser)
class DomaineUserAdmin(admin.ModelAdmin):
    list_display = ("user", "domaine", "is_admin", "created_at")
    list_filter = ("is_admin", "domaine")
    search_fields = ("user__email", "domaine__libelle")
    autocomplete_fields = ("user", "domaine")

