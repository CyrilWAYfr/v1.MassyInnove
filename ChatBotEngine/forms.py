from django import forms
from django.contrib.auth import get_user_model
from .models import AgentInstruction, MistralModel

User = get_user_model()

class AgentInstructionForm(forms.ModelForm):
    SHARING_CHOICES = [
        ("private", "Pour moi seulement"),
        ("public", "Pour tous les utilisateurs"),
        ("custom", "Certains utilisateurs seulement"),
    ]

    sharing_rule = forms.ChoiceField(
        choices=SHARING_CHOICES,
        label="Règles de partage",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    shared_with = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Utilisateurs à partager"
    )

    enable_image_tool = forms.BooleanField(
        required=False,
        label="Autoriser la génération d’images",
        help_text="Si activé, cet agent pourra générer des images via Mistral.",
        initial=False
    )

    enable_file_upload = forms.BooleanField(
        required=False,
        label="Autoriser le dépôt de fichiers",
        help_text="Si activé, les utilisateurs pourront déposer leurs fichiers dans une conversation avec cet agent.",
        initial=False
    )

    class Meta:
        model = AgentInstruction
        fields = [
            "title", "intro_text", "content",
            "mistral_model", "temperature", "top_p",
            "sharing_rule", "shared_with",
            "enable_image_tool", "enable_web_search", "enable_file_upload",
        ]
        labels = {
            "title": "Titre (visible par les utilisateurs)",
            "intro_text": "Texte introductif (visible par les utilisateurs)",
            "content": "Contenu des instructions (Prompt — invisible pour les utilisateurs)",
            "mistral_model": "Modèle Mistral",
            "temperature": "Température",
            "top_p": "Top P",
            "enable_image_tool": "Outil Image",
            "enable_web_search": "Autoriser la recherche web",
            "enable_file_upload": "Autoriser le dépôt de fichiers",
        }
        widgets = {
            "content": forms.Textarea(attrs={"rows": 6}),
            "intro_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Affichage prénom + nom + email
        self.fields["shared_with"].label_from_instance = (
            lambda obj: (
                f"{obj.first_name} {obj.last_name} – {obj.email}".strip()
                if (obj.first_name or obj.last_name) else obj.email
            )
        )

        # Préremplir sharing_rule selon instance
        if self.instance.pk:
            if self.instance.is_public:
                self.fields["sharing_rule"].initial = "public"
            elif self.instance.shared_with.exists():
                self.fields["sharing_rule"].initial = "custom"
            else:
                self.fields["sharing_rule"].initial = "private"
        else:
            self.fields["sharing_rule"].initial = "private"

        # Valeur par défaut du modèle Mistral si nouveau
        if not self.instance.pk and "mistral_model" in self.fields:
            try:
                self.fields["mistral_model"].initial = MistralModel.objects.get(id=2)
            except MistralModel.DoesNotExist:
                pass

        # Valeurs par défaut False pour les cases à cocher
        if not self.instance.pk:
            self.fields["enable_image_tool"].initial = False
            self.fields["enable_file_upload"].initial = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        rule = self.cleaned_data.get("sharing_rule")

        if rule == "public":
            instance.is_public = True
        else:
            instance.is_public = False

        if commit:
            instance.save()
        return instance
