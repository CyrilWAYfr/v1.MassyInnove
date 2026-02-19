from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.conf import settings
from ChatBotEngine.models import AgentInstruction

class Salutations(models.Model):
    libelle = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle


class Canal(models.Model):
    """
    Canal de contact (ex : email, téléphone, accueil, portail web…)
    """
    libelle = models.CharField(max_length=255)

    def __str__(self):
        return self.libelle

class StatutContact(models.Model):
    libelle = models.CharField(max_length=15, unique=True)

    def clean(self):
        if not self.libelle or not self.libelle.strip():
            raise ValidationError("Le libellé du statut ne peut pas être vide.")

    def __str__(self):
        return self.libelle


class Domaine(models.Model):
    libelle = models.CharField(max_length=255, unique=True)
    ordre = models.PositiveIntegerField(default=0)
    agent = models.ForeignKey(
        AgentInstruction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domaines",
        help_text="Agent IA utilisé pour la rédaction automatique des mails"
    )
    is_public = models.BooleanField(
        default=False,
        help_text="Domaine accessible à tous les utilisateurs de la plateforme"
    )
    intro = models.TextField(
        blank=True,
        help_text="Texte introductif ajoutée automatiquement au début des emails"
    )
    signature = models.TextField(
        blank=True,
        help_text="Signature ajoutée automatiquement à la fin des emails"
    )
    
    evaluation_reponse_obligatoire = models.BooleanField(
        default=False,
        help_text=(
            "Indique si l’évaluation de la réponse proposée par l’IA "
            "est obligatoire lors de la qualification d’un mail entrant."
        )
    )
    
    class Meta:
        ordering = ["ordre", "libelle"]

    def __str__(self):
        return self.libelle


class Groupe(models.Model):
    libelle = models.CharField(max_length=255)
    ordre = models.PositiveIntegerField(default=0)
    domaine = models.ForeignKey(
        Domaine,
        on_delete=models.CASCADE,
        related_name="groupes",
        null=False,     # ✔ de nouveau obligatoire
        blank=False     # ✔ obligatoire dans les formulaires
    )
    collapsed_by_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["domaine__ordre", "ordre", "libelle"]

    def __str__(self):
        return f"{self.domaine} / {self.libelle}"


class Thematique(models.Model):
    libelle_thematique = models.CharField(max_length=255)
    reponse_type = models.TextField(blank=True, null=True)
    ordre = models.PositiveIntegerField(default=0)
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name="thematiques",
        null=False,     # ✔ redevenu obligatoire
        blank=False
    )
    cocher_par_defaut = models.BooleanField(default=False)

    class Meta:
        ordering = [
            "groupe__domaine__ordre",
            "groupe__ordre",
            "ordre",
            "libelle_thematique",
        ]

    def __str__(self):
        return f"{self.groupe} / {self.libelle_thematique}"





class Demandeur(models.Model):
    email = models.EmailField(unique=True, blank=True, null=True)
    telephone = models.CharField(max_length=50, unique=True, blank=True, null=True)

    # Nouveau champ migré depuis Demande
    num_unique = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email or self.telephone or f"Demandeur {self.id}"

class EvaluationReponse(models.TextChoices):
        INCORRECT = "incorrect", "Incorrect"
        CORRECT_A_CORRIGER = "correct_a_corriger", "Correct avec corrections nécessaires"
        PARFAIT = "parfait", "Parfait"

class PieceJointeContactEntrant(models.Model):
    contact_entrant = models.ForeignKey(
        "ContactEntrant",
        on_delete=models.CASCADE,
        related_name="pieces_jointes",
    )

    nom_original = models.CharField(max_length=255)
    content_type = models.CharField(max_length=127, blank=True)
    taille = models.PositiveIntegerField(null=True, blank=True)

    contenu = models.BinaryField()  # <- le fichier en BDD

    created_at = models.DateTimeField(auto_now_add=True)


class ContactEntrant(models.Model):
    date = models.DateTimeField()
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT)
    
    external_message_id = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)

    domaine = models.ForeignKey(
        Domaine,
        on_delete=models.PROTECT,
        related_name="contacts_entrants"
    )

    demandeur = models.ForeignKey(
        Demandeur,
        on_delete=models.PROTECT,
        related_name="contacts_entrants"
    )
    
    salutation = models.ForeignKey(
        Salutations,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contacts_entrants"
    )


    objet = models.TextField(blank=True, null=True)
    txtdemande = models.TextField()

    thematiques = models.ManyToManyField(
        Thematique,
        blank=True,
        related_name="contacts_entrants"
    )
    
    reponse = models.TextField(null=True, blank=True)
    
    evaluation_reponse = models.CharField(
        max_length=32,
        choices=EvaluationReponse.choices,
        null=True,
        blank=True
    )
    
    statut = models.ForeignKey(
        StatutContact,
        on_delete=models.PROTECT,
        related_name="contacts_entrants",
        null=True,
        blank=True
    )

    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """
        Valide que selon le canal, le demandeur possède l'info obligatoire.
        Email obligatoire si canal = email
        Téléphone obligatoire si canal = téléphone
        """

        # --- Validation demandeur ---
        if not self.demandeur:
            raise ValidationError("Un contact entrant doit être associé à un demandeur.")

        lib = (self.canal.libelle or "").lower()

        # --- Canal Email → email obligatoire ---
        if "mail" in lib or "email" in lib:
            if not self.demandeur.email:
                raise ValidationError("Ce canal nécessite une adresse email renseignée.")

        # --- Canal Téléphone → téléphone obligatoire ---
        if "téléphone" in lib or "telephone" in lib or "tel" in lib:
            if not self.demandeur.telephone:
                raise ValidationError("Ce canal nécessite un numéro de téléphone renseigné.")

        # --- Statut par défaut ---
        if self.statut is None:
            from .models import StatutContact
            try:
                self.statut = StatutContact.objects.get(pk=1)
            except StatutContact.DoesNotExist:
                raise ValidationError(
                    "Le statut par défaut (ID=1) est introuvable. "
                    "Veuillez le créer avant d'enregistrer un contact."
                )


    def __str__(self):
        canal = self.canal.libelle if self.canal else "?"
        statut = self.statut.libelle if self.statut else "?"
        domaine = self.domaine.libelle if self.domaine else "?"
        demandeur = str(self.demandeur) if self.demandeur else "?"
        date_str = self.date.strftime("%d/%m/%Y %H:%M") if self.date else "?"

        return f"{domaine} / {canal} de {demandeur} du {date_str}"


class DomaineUser(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="logement_domaines_links"
    )
    domaine = models.ForeignKey(
        Domaine,
        on_delete=models.CASCADE,
        related_name="user_links"
    )
    is_admin = models.BooleanField(
        default=False,
        help_text="Administrateur fonctionnel de ce domaine (Groupes/Thématiques)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "domaine"], name="uniq_user_domaine")
        ]
        ordering = ["domaine__ordre", "domaine__libelle", "user__username"]

    def __str__(self):
        role = "admin" if self.is_admin else "user"
        return f"{self.user} → {self.domaine} ({role})"

class BlacklistedSender(models.Model):
    ENTRY_TYPE_EMAIL = "email"
    ENTRY_TYPE_DOMAIN = "domain"
    ENTRY_TYPE_CHOICES = (
        (ENTRY_TYPE_EMAIL, "Adresse email"),
        (ENTRY_TYPE_DOMAIN, "Domaine"),
    )

    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    value = models.CharField(max_length=255, db_index=True)
    domaine = models.ForeignKey(
        Domaine,
        on_delete=models.CASCADE,
        related_name="blacklisted_senders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logement_blacklist_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domaine", "entry_type", "value"],
                name="uniq_blacklisted_sender_domain_type_value",
            )
        ]
        ordering = ["domaine__ordre", "domaine__libelle", "entry_type", "value"]

    def clean(self):
        normalized = (self.value or "").strip().lower()
        if not normalized:
            raise ValidationError("La valeur de liste noire ne peut pas etre vide.")

        if self.entry_type == self.ENTRY_TYPE_EMAIL:
            validate_email(normalized)
        elif self.entry_type == self.ENTRY_TYPE_DOMAIN:
            if "@" in normalized:
                raise ValidationError("Un domaine ne doit pas contenir '@'.")
            parts = normalized.split(".")
            if len(parts) < 2 or any(not part or len(part) > 63 for part in parts):
                raise ValidationError("Le domaine indique est invalide.")
            for part in parts:
                if not part.replace("-", "").isalnum() or part.startswith("-") or part.endswith("-"):
                    raise ValidationError("Le domaine indique est invalide.")
        else:
            raise ValidationError("Type d'entree invalide pour la liste noire.")

    def save(self, *args, **kwargs):
        self.value = (self.value or "").strip().lower().lstrip("@")
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.domaine} / {self.get_entry_type_display()} : {self.value}"

    @classmethod
    def is_sender_blacklisted(cls, *, sender_email: str, domaine_id: int) -> bool:
        normalized_email = (sender_email or "").strip().lower()
        if not normalized_email or "@" not in normalized_email:
            return False

        domain = normalized_email.rsplit("@", 1)[1]
        return cls.objects.filter(
            domaine_id=domaine_id
        ).filter(
            models.Q(entry_type=cls.ENTRY_TYPE_EMAIL, value=normalized_email)
            | models.Q(entry_type=cls.ENTRY_TYPE_DOMAIN, value=domain)
        ).exists()
