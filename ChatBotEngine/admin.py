
# admin.py
from django.contrib import admin
from .models import AgentInstruction, MistralModel



@admin.register(MistralModel)
class MistralModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(AgentInstruction)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'mistral_model',
        'temperature',
        'top_p',
        'owner',
        'created_at',
        'updated_at',
    )
    list_filter = ('mistral_model', 'created_at', 'updated_at', 'owner')  # filtre aussi par owner
    search_fields = ('title', 'content', 'owner__email', 'owner__username')
    autocomplete_fields = ('owner',)  # pratique si beaucoup d'utilisateurs

    
from django.contrib import admin
from .models import Conversation, Message

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "agent_name", "title", "is_persistent", "messages_count", "last_activity_at", "created_at")
    list_filter = ("is_persistent", "archived_at")
    search_fields = ("id", "owner__email", "owner__username", "title", "agent_name")
    date_hierarchy = "created_at"
    ordering = ("-last_activity_at",)
    readonly_fields = ("created_at", "last_activity_at", "messages_count", "tokens_input_total", "tokens_output_total")

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "model", "tokens_input", "tokens_output", "created_at")
    list_filter = ("role", "model")
    search_fields = ("conversation__id", "content")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

# ChatBotEngine/views_admin_libraries.py
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from mistralai import Mistral
from .models import AgentInstruction
import logging

logger = logging.getLogger(__name__)

def _is_staff(user):
    return user.is_authenticated and user.is_staff

