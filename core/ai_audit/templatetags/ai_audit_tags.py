from django import template
from core.ai_audit.models import AiCallLog

register = template.Library()

@register.simple_tag(takes_context=True)
def ai_usage_count(context):
    user = context.get("user")
    if not user or not user.is_authenticated:
        return 0
    return AiCallLog.objects.filter(user=user).count()
