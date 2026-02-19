from django import forms
from .models import Canal, Thematique, StatutContact, Domaine, Groupe, Salutations, BlacklistedSender
from django.utils import timezone


class CanalForm(forms.ModelForm):
    class Meta:
        model = Canal
        fields = ["libelle"]
        widgets = {
            "libelle": forms.TextInput(attrs={"class": "form-control"})
        }


class ThematiqueForm(forms.ModelForm):
    class Meta:
        model = Thematique
        fields = ["libelle_thematique", "groupe", "ordre", "reponse_type", "cocher_par_defaut"]
        widgets = {
            "libelle_thematique": forms.TextInput(attrs={"class": "form-control"}),
            "groupe": forms.Select(attrs={"class": "form-control"}),
            "ordre": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "reponse_type": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }



# logement/forms.py
from django import forms
from django.utils import timezone
from .models import Canal, StatutContact


class EmailEntrantStep1Form(forms.Form):
    date = forms.DateField(
        label="Date du contact",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "form-control", "style": "width:150px;"}
        ),
    )

    canal = forms.ModelChoiceField(
        label="Canal",
        queryset=Canal.objects.all(),
        empty_label=None,
    )


    statut = forms.ModelChoiceField(
        label="Statut",
        queryset=StatutContact.objects.all().order_by("id"),
        empty_label=None,
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "style": "width:160px;"})
    )

    email = forms.EmailField(label="Email expéditeur", required=True)

    objet = forms.CharField(label="Objet", required=False)
    texte = forms.CharField(label="Message", widget=forms.Textarea, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound:
            # Valeur par défaut : aujourd'hui
            self.initial["date"] = timezone.localdate().strftime("%Y-%m-%d")

            # Valeur par défaut : canal ID = 3
            self.initial["canal"] = 3

            # ⭐ Valeur par défaut : statut ID = 1
            self.initial["statut"] = 1




class EmailEntrantStep2Form(forms.Form):
    
    salutation = forms.ModelChoiceField(
        label="Salutation",
        queryset=Salutations.objects.all().order_by("libelle"),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm select-compact",
        }),
    )

    numero_unique = forms.CharField(
        label="Numéro unique",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "style": "width: 120px; text-align: right; padding-right: 4px;"
        })
    )


    thematiques = forms.ModelMultipleChoiceField(
        queryset=Thematique.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    reponse = forms.CharField(
        label="Réponse",
        required=False,
        widget=forms.Textarea(attrs={"rows": 6, "id": "id_reponse"})
    )
    
    statut = forms.ModelChoiceField(
        label="Statut",
        queryset=StatutContact.objects.all().order_by("id"),
        empty_label=None,
        required=True,
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm select-compact",
        }),
    )

    evaluation_reponse = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )


## Demandeurs

from django import forms
from .models import Demandeur


class DemandeurForm(forms.ModelForm):
    class Meta:
        model = Demandeur
        fields = ["email", "telephone", "num_unique"]

        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "num_unique": forms.TextInput(attrs={"class": "form-control"}),
        }


## GROUPES ET DOMAINES

class GroupeForm(forms.ModelForm):
    class Meta:
        model = Groupe
        fields = ["libelle", "ordre", "domaine", "collapsed_by_default"]
        widgets = {
            "domaine": forms.Select(attrs={"class": "form-control"}),
            "libelle": forms.TextInput(attrs={"class": "form-control"}),
            "ordre": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "collapsed_by_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

class DomaineForm(forms.ModelForm):
    class Meta:
        model = Domaine
        fields = [
            "libelle",
            "ordre",
            "is_public",
            "agent",
            "intro",
            "signature",
            "evaluation_reponse_obligatoire",
        ]
        widgets = {
            "libelle": forms.TextInput(attrs={"class": "form-control"}),
            "ordre": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "agent": forms.Select(attrs={"class": "form-control"}),
            "signature": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "intro": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "evaluation_reponse_obligatoire": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }




## Salutations

from django import forms
from .models import Salutations


class SalutationForm(forms.ModelForm):
    class Meta:
        model = Salutations
        fields = ["libelle"]
        widgets = {
            "libelle": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": 20,
                "placeholder": "Ex : Madame, Monsieur, Bonjour..."
            })
        }
        labels = {
            "libelle": "Libellé",
        }

class BlacklistedSenderForm(forms.ModelForm):
    class Meta:
        model = BlacklistedSender
        fields = ["entry_type", "value"]
        widgets = {
            "entry_type": forms.Select(attrs={"class": "form-select"}),
            "value": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex: bob@mycompany.com ou mycompany.com",
                }
            ),
        }
        labels = {
            "entry_type": "Type d'entree",
            "value": "Valeur",
        }
