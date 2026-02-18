# core/ai_audit/services.py
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Optional, Dict, Any

from django.apps import apps
from .models import AiCallLog

# 1,5 mg = 0,0015 g CO₂ par token
CO2_GRAMS_PER_TOKEN = Decimal("0.0015")


def hash_request(text: str, salt: Optional[str] = None) -> str:
    """Hache le texte (prompt) pour traçabilité sans stockage en clair (BLAKE2b)."""
    if not text:
        return ""
    h = hashlib.blake2b(digest_size=32)
    if salt:
        h.update(salt.encode("utf-8"))
    h.update(text.encode("utf-8"))
    return h.hexdigest()


@lru_cache(maxsize=128)
def _get_mistral_pricing(model_name: str):
    """
    Récupère (input_cost, output_cost) depuis ChatBotEngine.MistralModel.
    Les coûts sont stockés PAR 1_000_000 tokens.
    """
    try:
        MistralModel = apps.get_model("ChatBotEngine", "MistralModel")
    except LookupError:
        return None

    try:
        mm = MistralModel.objects.get(name=model_name)
    except MistralModel.DoesNotExist:
        return None

    inp = Decimal(str(mm.input_cost or 0))
    out = Decimal(str(mm.output_cost or 0))
    return inp, out


def compute_cost_and_impact(model_name: str, tokens_input: int, tokens_output: int):
    """
    Calcule (cost_eur, co2_grams, tokens_total) à partir du pricing ChatBotEngine.MistralModel.
    - input_cost/output_cost : PAR 1_000_000 tokens
    - CO₂ : 1,5 mg / token
    """
    tokens_input = int(tokens_input or 0)
    tokens_output = int(tokens_output or 0)
    tokens_total = tokens_input + tokens_output

    pricing = _get_mistral_pricing(model_name)
    if pricing is not None:
        inp_cost_1M, out_cost_1M = pricing
        cost = (
            (Decimal(tokens_input) * inp_cost_1M / Decimal(1_000_000))
            + (Decimal(tokens_output) * out_cost_1M / Decimal(1_000_000))
        )
    else:
        cost = Decimal("0")

    co2 = Decimal(tokens_total) * CO2_GRAMS_PER_TOKEN

    # Arrondis agréables (même granularité que le modèle)
    cost = cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    co2 = co2.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    return cost, co2, tokens_total


def log_ai_call(
    *,
    user,
    model: str,
    tokens_input: int,
    tokens_output: int,
    source_app: str = "ChatBotEngine",
    source_module: str = "",
    provider: str = "mistral",
    request_hash: str = "",
    latency_ms: int = 0,
    status: str = AiCallLog.Status.SUCCESS,
    metadata: Optional[Dict[str, Any]] = None,
    cost_eur: Optional[Decimal | float | str] = None,
    co2_grams: Optional[Decimal | float | str] = None,
) -> AiCallLog:
    """
    Enregistre un appel IA.
    - Si cost_eur est fourni => on le respecte (alignement parfait avec ton UX).
    - Sinon => calcul automatique via ChatBotEngine.MistralModel (pricing par 1M).
    - co2_grams est toujours calculable automatiquement si absent.
    """
    # Calculs / normalisations
    tokens_input = int(tokens_input or 0)
    tokens_output = int(tokens_output or 0)
    tokens_total = tokens_input + tokens_output

    # Coût & CO2
    if cost_eur is None or co2_grams is None:
        auto_cost, auto_co2, _ = compute_cost_and_impact(model, tokens_input, tokens_output)
        if cost_eur is None:
            cost_eur = auto_cost
        else:
            cost_eur = Decimal(str(cost_eur))
        if co2_grams is None:
            co2_grams = auto_co2
        else:
            co2_grams = Decimal(str(co2_grams))
    else:
        # Normalise types
        cost_eur = Decimal(str(cost_eur))
        co2_grams = Decimal(str(co2_grams))

    return AiCallLog.objects.create(
        user=user,
        source_app=source_app,
        source_module=source_module,
        provider=provider,
        model=model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_total,
        cost_eur=cost_eur,
        co2_grams=co2_grams,
        request_hash=request_hash,
        latency_ms=int(latency_ms or 0),
        status=status,
        metadata=metadata or {},
    )

###################             CALCUL DES COÛTS POUR LES APPELS MISTRAL       ###############################

from decimal import Decimal

# Prix fixes en euros pour les modèles (exemple, à adapter selon vos données)
MODEL_PRICING_EUR = {
    "mistral-tiny": {"input": Decimal("0.000002"), "output": Decimal("0.000006")},
    "mistral-small": {"input": Decimal("0.000002"), "output": Decimal("0.000006")},
    "mistral-medium": {"input": Decimal("0.000003"), "output": Decimal("0.000009")},
    # Ajoutez d'autres modèles ici
}

# Prix fixes en euros pour les connecteurs
CONNECTOR_PRICING_EUR = {
    "image_generation": Decimal("0.092"),
    "web_search": Decimal("0.028"),
}

def compute_cost(usage, model) -> Decimal:
    """Calcule le coût total en EUR pour un appel Mistral."""
    if not usage or not model:
        return Decimal("0.0")

    # Récupération des tokens (accès direct aux attributs)
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    # Récupération des coûts du modèle (par nom de modèle)
    model_name = getattr(model, "name", str(model))
    model_pricing = MODEL_PRICING_EUR.get(model_name, {"input": Decimal("0.0"), "output": Decimal("0.0")})
    input_cost_eur = (Decimal(input_tokens) / Decimal(1_000_000)) * model_pricing["input"]
    output_cost_eur = (Decimal(output_tokens) / Decimal(1_000_000)) * model_pricing["output"]

    # Coût des connecteurs
    connector_cost_eur = Decimal("0.0")
    # Vérification si l'attribut `connectors` existe et n'est pas Unset
    if hasattr(usage, "connectors") and getattr(usage, "connectors", None) is not None:
        connectors = getattr(usage, "connectors", {})
        if isinstance(connectors, dict):
            for connector, count in connectors.items():
                unit_price = CONNECTOR_PRICING_EUR.get(connector, Decimal("0"))
                connector_cost_eur += Decimal(count) * unit_price

    total_eur = input_cost_eur + output_cost_eur + connector_cost_eur
    return total_eur.quantize(Decimal("0.00001"))
