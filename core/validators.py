from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_domain_email(value):
    if not value.lower().endswith("@mairie-massy.fr"):
        raise ValidationError(
            _("%(value)s n'est pas un email autorisé. "
              "Vous devez utiliser votre adresse mail @mairie-massy.fr pour vous créer un compte !"),
            params={"value": value},
        )
