import json
from django.db import transaction
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime

from logement.models import ContactEntrant, PieceJointeContactEntrant, Demandeur, BlacklistedSender, Domaine
from .auth import api_key_required


CANAL_MAIL_ID = 1  # ✅ confirmé: id du canal "Mail"


def _bad_request(msg: str, **extra):
    payload = {"ok": False, "error": msg}
    payload.update(extra)
    return JsonResponse(payload, status=400)


@csrf_exempt
@api_key_required
def ingest_contact_entrant(request: HttpRequest):
    """
    POST multipart/form-data
      - payload: JSON string
      - attachments: 0..n fichiers (champ répétable)

    payload minimal:
    {
      "external_message_id": "...",
      "sender": "foo@bar.com",
      "received_at": "2026-02-10T10:30:00Z",
      "domaine_id": 2,
      "statut_id": 1,                 # <- nouveau
      "subject": "...",               # optionnel
      "body_text": "..."              # optionnel
    }
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    payload_raw = request.POST.get("payload")
    if not payload_raw:
        return _bad_request("Missing 'payload' field (JSON string)")

    try:
        data = json.loads(payload_raw)
    except json.JSONDecodeError:
        return _bad_request("Invalid JSON in 'payload'")

    external_message_id = (data.get("external_message_id") or "").strip()
    if not external_message_id:
        return _bad_request("external_message_id is required for ingestion")

    sender = (data.get("sender") or "").strip().lower()
    if not sender:
        return _bad_request("sender is required to create Demandeur")

    domaine_id = data.get("domaine_id")
    if not isinstance(domaine_id, int):
        return _bad_request("domaine_id must be an integer")
    if not Domaine.objects.filter(id=domaine_id).exists():
        return _bad_request("domaine_id is invalid")

    statut_id = data.get("statut_id", None)
    if statut_id is not None and not isinstance(statut_id, int):
        return _bad_request("statut_id must be an integer or null")

    received_at_raw = data.get("received_at")
    if not received_at_raw:
        return _bad_request("received_at is required (ISO 8601 datetime)")
    received_at = parse_datetime(received_at_raw)
    if received_at is None:
        return _bad_request("received_at must be a valid ISO 8601 datetime", received_at=received_at_raw)

    subject = data.get("subject")
    body_text = data.get("body_text")

    files = request.FILES.getlist("attachments")

    with transaction.atomic():
        demandeur, _ = Demandeur.objects.get_or_create(email=sender)

        ce, created = ContactEntrant.objects.get_or_create(
            external_message_id=external_message_id,
            defaults=dict(
                date=received_at,
                canal_id=CANAL_MAIL_ID,
                domaine_id=domaine_id,
                demandeur=demandeur,
                salutation_id=None,
                objet=(subject or ""),
                txtdemande=(body_text or ""),
                statut_id=statut_id,
            ),
        )

        # Si déjà existant, on ne touche pas (idempotence stricte).
        # Si tu veux quand même mettre à jour le statut quand created=False, dis-le.
        if created:
            for f in files:
                PieceJointeContactEntrant.objects.create(
                    contact_entrant=ce,
                    nom_original=f.name,
                    content_type=getattr(f, "content_type", "") or "",
                    taille=getattr(f, "size", None),
                    contenu=f.read(),
                )

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "contact_entrant_id": ce.id,
            "pieces_jointes_count": ce.pieces_jointes.count(),
        },
        status=201 if created else 200,
    )


#Pour import contactentrant avec PJ facilité côté N8N

import base64
import binascii
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime

from logement.models import ContactEntrant, Demandeur, PieceJointeContactEntrant


# -----------------------------
# À ADAPTER : même auth que l'endpoint multipart existant
# -----------------------------
def check_api_key(request) -> bool:
    """
    Retourne True si la clé API est valide.
    - X-API-Key: <token>
    - ou Authorization: Bearer <token>
    """
    token = request.headers.get("X-API-Key", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()

    # TODO: branche ça sur ton settings. Ex:
    # from django.conf import settings
    # return token and token == settings.INGEST_API_KEY
    from django.conf import settings
    return bool(token) and token == getattr(settings, "INGEST_API_KEY", None)


def json_error(status: int, msg: str):
    return JsonResponse({"ok": False, "error": msg}, status=status)


# limites simples (tu peux ajuster)
MAX_ATTACHMENTS = 30
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024     # 10 MB par pièce jointe
MAX_TOTAL_BYTES = 30 * 1024 * 1024          # 30 MB total


@csrf_exempt
@require_POST
def ingest_contact_entrant_json(request):
    """
    Body: application/json
    {
      "payload": { ... },                         # dict, pas string
      "attachments": [
        {"filename": "...", "content_type":"...", "data_base64":"..."},
        ...
      ]
    }
    """

    if not check_api_key(request):
        # garde le même message que ton API actuelle si tu veux
        return json_error(401, "Invalid API token")

    # --------- parse JSON ---------
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return json_error(400, "Invalid JSON body")

    payload = body.get("payload")
    if not isinstance(payload, dict):
        return json_error(400, "Missing or invalid 'payload' (object expected)")

    attachments = body.get("attachments", [])
    if attachments is None:
        attachments = []
    if not isinstance(attachments, list):
        return json_error(400, "Invalid 'attachments' (array expected)")

    if len(attachments) > MAX_ATTACHMENTS:
        return json_error(400, f"Too many attachments (max {MAX_ATTACHMENTS})")

    # --------- validate payload ---------
    external_message_id = payload.get("external_message_id")
    sender = payload.get("sender")
    received_at = payload.get("received_at")
    domaine_id = payload.get("domaine_id")
    statut_id = payload.get("statut_id", None)

    subject = payload.get("subject") or ""
    body_text = payload.get("body_text") or ""

    if not external_message_id or not isinstance(external_message_id, str):
        return json_error(400, "Missing/invalid external_message_id")
    if not sender or not isinstance(sender, str):
        return json_error(400, "Missing/invalid sender")
    if not received_at or not isinstance(received_at, str):
        return json_error(400, "Missing/invalid received_at")
    if not isinstance(domaine_id, int):
        return json_error(400, "Missing/invalid domaine_id")

    dt = parse_datetime(received_at)
    if dt is None:
        return json_error(400, "Invalid received_at (ISO datetime expected)")

    # --------- idempotence ---------
    existing = ContactEntrant.objects.filter(external_message_id=external_message_id).first()
    if existing:
        # ne réimporte pas les PJ en retry
        return JsonResponse({
            "ok": True,
            "created": False,
            "contact_entrant_id": existing.id,
            "pieces_jointes_count": existing.pieces_jointes.count(),
        }, status=200)

    # --------- demandeur : get-or-create par email ---------
    demandeur = Demandeur.objects.filter(email=sender).first()
    if not demandeur:
        demandeur = Demandeur.objects.create(email=sender)

    # --------- create ContactEntrant ---------
    contact = ContactEntrant.objects.create(
        external_message_id=external_message_id,
        date=dt,
        canal_id=1,               # Mail
        domaine_id=domaine_id,
        demandeur=demandeur,
        objet=subject,
        txtdemande=body_text,
        statut_id=statut_id,
        salutation=None,
    )

    # --------- attachments base64 -> BinaryField ---------
    total_bytes = 0
    saved = 0

    for att in attachments:
        if not isinstance(att, dict):
            continue

        filename = (att.get("filename") or "").strip() or "attachment"
        content_type = (att.get("content_type") or "").strip()
        data_b64 = att.get("data_base64")

        if not data_b64 or not isinstance(data_b64, str):
            continue

        # decode base64 (strict)
        try:
            raw = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError):
            return json_error(400, "Invalid base64 in attachments")

        size = len(raw)
        if size > MAX_ATTACHMENT_BYTES:
            return json_error(400, f"Attachment too large: {filename}")

        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            return json_error(400, "Total attachments size too large")

        PieceJointeContactEntrant.objects.create(
            contact_entrant=contact,
            nom_original=filename[:255],
            content_type=content_type[:127],
            taille=size,
            contenu=raw,
        )
        saved += 1

    return JsonResponse({
        "ok": True,
        "created": True,
        "contact_entrant_id": contact.id,
        "pieces_jointes_count": saved,
    }, status=201)


@csrf_exempt
@api_key_required
def check_sender_authorization(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads((request.body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _bad_request("Invalid JSON body")

    sender = (data.get("sender") or "").strip().lower()
    if not sender:
        return _bad_request("sender is required")

    domaine_id = data.get("domaine_id")
    if not isinstance(domaine_id, int):
        return _bad_request("domaine_id must be an integer")
    if not Domaine.objects.filter(id=domaine_id).exists():
        return _bad_request("domaine_id is invalid")

    if "@" not in sender:
        return _bad_request("sender must be a fully-formed email address")

    is_blocked = BlacklistedSender.is_sender_blacklisted(
        sender_email=sender,
        domaine_id=domaine_id,
    )
    return JsonResponse(
        {
            "ok": True,
            "authorized": not is_blocked,
        },
        status=200,
    )
