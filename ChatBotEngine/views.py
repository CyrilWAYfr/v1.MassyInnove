from django.shortcuts import render
import requests

def hello_world(request):
    return render(request, 'hello_world.html')


import os
from django.shortcuts import render
from mistralai import Mistral
from .models import AgentInstruction, MistralModel
from core.models import FileAsset
from django.db import connection


####################    PROXI POUR LE RENVOI D'URL Mistral      ##########################

from django.http import HttpResponse
from django.views.decorators.http import require_GET
import requests
from django.conf import settings

@require_GET
def mistral_file_proxy(request, file_id):
	"""
	Proxy pour récupérer un fichier généré par Mistral (image, etc.).
	Le serveur ajoute l'Authorization et renvoie le binaire avec un Content-Type correct.
	"""
	url = f"https://api.mistral.ai/v1/files/{file_id}/content"
	headers = {"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"}
	r = requests.get(url, headers=headers, stream=True)

	if r.status_code != 200:
		# L'image n'est plus disponible → réponse claire
		return HttpResponse("Image expirée", status=410, content_type="text/plain")

	# Déterminer le bon Content-Type
	content_type = r.headers.get("Content-Type") or "image/png"
	if content_type == "application/octet-stream":
		content_type = "image/png"  # fallback par défaut

	# Nom de fichier explicite
	file_name = f"image_mistral.{content_type.split('/')[-1]}"

	response = HttpResponse(r.content, content_type=content_type)
	response["Content-Disposition"] = f'inline; filename=\"{file_name}\"'
	return response






####################    CHAT PERSISTANT      ##########################

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Conversation


def my_conversations(request):
    conversations = Conversation.objects.filter(owner=request.user).order_by("-last_activity_at")
    paginator = Paginator(conversations, 10)  # 10 par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "ChatBotEngine/my_conversations.html",
        {"page_obj": page_obj}
    )

from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from mistralai import Mistral
from ChatBotEngine.models import Conversation
import logging

logger = logging.getLogger(__name__)

def delete_conversation(request, pk):
    """
    Supprime une conversation :
    - En base locale
    - Côté Mistral (conversation_id)
    - Supprime aussi l’agent cloné temporaire et sa librairie Mistral le cas échéant
    """
    conv = get_object_or_404(Conversation, pk=pk, owner=request.user)

    if request.method != "POST":
        return HttpResponseForbidden("Suppression non autorisée par GET.")

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    try:
        # 1️⃣ Supprimer la conversation côté Mistral
        if conv.mistral_conversation_id:
            try:
                client.beta.conversations.delete(conversation_id=conv.mistral_conversation_id)
                logger.info(f"Conversation Mistral supprimée : {conv.mistral_conversation_id}")
            except Exception as e:
                logger.warning(f"Échec suppression conversation Mistral ({conv.mistral_conversation_id}) : {e}")

        # 2️⃣ Si cette conversation utilisait un agent temporaire (clone)
        agent = getattr(conv, "agent_instruction", None)
        if agent and (agent.is_temporary or agent.is_clone()):
            logger.info(f"Suppression de l’agent temporaire {agent.id} ({agent.title})")

            # Supprimer la librairie Mistral de cet agent
            if agent.mistral_library_id:
                try:
                    client.beta.libraries.delete(library_id=agent.mistral_library_id)
                    logger.info(f"Librairie Mistral supprimée : {agent.mistral_library_id}")
                except Exception as e:
                    logger.warning(f"Échec suppression librairie Mistral ({agent.mistral_library_id}) : {e}")

            # Supprimer aussi l’agent côté Mistral s’il existe
            if agent.mistral_agent_id:
                try:
                    client.agents.delete(agent_id=agent.mistral_agent_id)
                    logger.info(f"Agent Mistral supprimé : {agent.mistral_agent_id}")
                except Exception as e:
                    logger.warning(f"Échec suppression agent Mistral ({agent.mistral_agent_id}) : {e}")

            # Supprimer le clone localement
            try:
                agent.delete()
                logger.info(f"Agent cloné supprimé localement : {agent.id}")
            except Exception as e:
                logger.warning(f"Échec suppression agent local : {e}")

        # 3️⃣ Supprimer enfin la conversation locale
        conv.delete()
        messages.success(request, "Conversation et ressources associées supprimées avec succès.")

    except Exception as e:
        logger.exception(f"Erreur lors de la suppression de la conversation {pk}: {e}")
        messages.error(request, f"Erreur lors de la suppression : {e}")

    return redirect("chatbotengine:my_conversations")



####################    LISTE des CHATBOTS      ##########################

from django.db.models import Q

def chatbot_list(request):
    user = request.user

    # Mes agents personnels (hors clones)
    my_agents = AgentInstruction.objects.filter(
        owner=user,
        source_agent__isnull=True  # ✅ exclut les clones
    )

    # Agents partagés avec moi (inchangé)
    shared_agents = AgentInstruction.objects.filter(
        Q(is_public=True) | Q(shared_with=user)
    ).exclude(owner=user).distinct()

    return render(request, "ChatBotEngine/chatbot_list.html", {
        "my_agents": my_agents,
        "shared_agents": shared_agents,
    })


####################    CREATION/MAJ/SUPPR d'un CHATBOT      ##########################

## HELPERS ##

# --- Helpers MINIMAUX de sync Agent <-> Mistral ---
import requests
from django.conf import settings
from mistralai import Mistral
from ChatBotEngine.helpers import get_or_create_agent_library

_MISTRAL_BASE = "https://api.mistral.ai/v1"
def _headers():
    return {"Authorization": f"Bearer {settings.MISTRAL_API_KEY}", "Content-Type": "application/json"}

def _build_agent_payload(instructions) -> dict:
    tools = []
    if getattr(instructions, "enable_web_search", False):
        tools.append({"type": "web_search"})
    if getattr(instructions, "enable_image_tool", False):
        tools.append({"type": "image_generation"})

    # Librairie documentaire (on garde le try/except, on LOG uniquement)
    try:
        lib_id = get_or_create_agent_library(instructions)
        if lib_id:
            tools.append({"type": "document_library", "library_ids": [lib_id]})
    except Exception as e:
        import logging
        logging.exception(
            "Library setup FAILED for agent %s (title=%r).",
            getattr(instructions, "id", None),
            getattr(instructions, "title", None),
        )

    payload = {
        "name": instructions.title or "Agent",
        "instructions": f"{(instructions.content or '').strip()}",
        "model": (instructions.mistral_model.name if instructions.mistral_model_id else "mistral-large-latest"),
        "completion_args": {"temperature": instructions.temperature, "top_p": instructions.top_p},
    }
    if tools:
        payload["tools"] = tools

    # 👇 Ajout de log (info) pour voir ce qu’on s’apprête à envoyer
    try:
        import logging
        logging.info("Agent payload tools=%s", payload.get("tools"))
    except Exception:
        pass

    return payload



############   CREATION / MODIFICATION / SUPPRESSION DE L'AGENT COTE MISTRAL


from ChatBotEngine.utils import _build_agent_directive

def ensure_agent_exists_on_mistral(instructions) -> str:
    """
    Crée l’agent chez Mistral si pas encore fait ; retourne son ID.
    Injecte automatiquement la directive de formatage JSON structuré.
    """
    if getattr(instructions, "mistral_agent_id", None):
        return instructions.mistral_agent_id

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # 🧩 Construire le contenu enrichi
    formatted_content = _build_agent_directive(instructions.content)

    # ⚙️ Construire le payload standard (avec contenu enrichi)
    payload = _build_agent_payload(instructions)
    payload["instructions"] = formatted_content

    # 🪄 Créer l’agent Mistral
    agent = client.beta.agents.create(**payload)

    # 🧱 Sauvegarde locale
    instructions.mistral_agent_id = agent.id
    instructions.save(update_fields=["mistral_agent_id"])

    return agent.id



def update_agent_on_mistral(instructions) -> None:
    """
    Met à jour un agent Mistral existant avec la directive JSON standard.
    Si l'agent n'existe plus côté Mistral, il est recréé.
    """
    # 🧩 Injecter la directive enrichie
    formatted_content = _build_agent_directive(instructions.content)

    payload = _build_agent_payload(instructions)
    payload["instructions"] = formatted_content  # 👈 remplace le texte original

    if getattr(instructions, "mistral_agent_id", None):
        try:
            r = requests.patch(
                f"{_MISTRAL_BASE}/agents/{instructions.mistral_agent_id}",
                json=payload,
                headers=_headers(),
                timeout=30
            )

            if r.status_code == 404:
                raise RuntimeError("missing_remote")

            r.raise_for_status()
            return  # ✅ succès

        except Exception as e:
            logger.warning(f"⚠️ update_agent_on_mistral: échec PATCH ({e}), recréation...")

    # 🧱 fallback → (re)création complète si PATCH échoué
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    agent = client.beta.agents.create(**payload)
    instructions.mistral_agent_id = agent.id
    instructions.save(update_fields=["mistral_agent_id"])



def delete_agent_on_mistral(instructions) -> None:
    """DELETE best-effort; ignore erreurs (ex. déjà supprimé)."""
    aid = getattr(instructions, "mistral_agent_id", None)
    if not aid:
        return
    try:
        requests.delete(f"{_MISTRAL_BASE}/agents/{aid}", headers=_headers(), timeout=20)
    except Exception:
        pass


##### MAIN #####

from django.contrib import messages
from .forms import AgentInstructionForm

def create_chatbot(request):
    if request.method == "POST":
        form = AgentInstructionForm(request.POST)
        if form.is_valid():
            chatbot = form.save(commit=False)
            chatbot.owner = request.user
            chatbot.save()  # l'objet a maintenant un id

            # Partage
            rule = form.cleaned_data.get("sharing_rule")
            if rule == "custom":
                chatbot.shared_with.set(form.cleaned_data["shared_with"])
            else:
                chatbot.shared_with.clear()

            # Création agent Mistral (best effort)
            try:
                ensure_agent_exists_on_mistral(chatbot)
            except Exception as e:
                messages.warning(
                    request,
                    f"Agent créé localement, mais la création Mistral a échoué : {e}"
                )

            # ➜ NOUVEAU : enchaîner directement vers la gestion des fichiers
            if "save_and_manage_files" in request.POST:
                return redirect("chatbotengine:agent_files", chatbot.pk)

            return redirect("chatbotengine:chatbot_list")
    else:
        form = AgentInstructionForm()

    return render(request, "ChatBotEngine/chatbot_form.html", {"form": form})





from django.contrib import messages  # si pas déjà importé

def update_chatbot(request, pk):
    chatbot = get_object_or_404(AgentInstruction, pk=pk)

    if chatbot.owner != request.user:
        return HttpResponseForbidden("Vous n’êtes pas autorisé à modifier cet agent IA.")

    if request.method == "POST":
        form = AgentInstructionForm(request.POST, instance=chatbot)
        if form.is_valid():
            chatbot = form.save(commit=False)
            chatbot.save()

            rule = form.cleaned_data.get("sharing_rule")
            if rule == "custom":
                chatbot.shared_with.set(form.cleaned_data["shared_with"])
            else:
                chatbot.shared_with.clear()

            # MàJ côté Mistral (best effort)
            try:
                update_agent_on_mistral(chatbot)
            except Exception as e:
                messages.warning(request, f"Mise à jour Mistral non appliquée : {e}")

            # ➜ NOUVEAU : aller gérer les fichiers si demandé
            if "save_and_manage_files" in request.POST:
                return redirect("chatbotengine:agent_files", chatbot.pk)

            return redirect("chatbotengine:chatbot_list")
    else:
        form = AgentInstructionForm(instance=chatbot)

    return render(request, "ChatBotEngine/chatbot_form.html", {
        "form": form,
        "mistral_agent_id": chatbot.mistral_agent_id,
        "mistral_library_id": chatbot.mistral_library_id,
    })




from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import AgentInstruction


def delete_chatbot(request, pk):
    chatbot = get_object_or_404(AgentInstruction, pk=pk)

    # Seul le créateur peut supprimer
    if chatbot.owner != request.user:
        return HttpResponseForbidden("Vous n’êtes pas autorisé à supprimer cet agent IA.")

    if request.method == "POST":
        try:
            # ⬇️ suppression côté Mistral (ignore les erreurs réseau/404)
            delete_agent_on_mistral(chatbot)
        except Exception as e:
            messages.warning(request, f"Suppression distante Mistral non confirmée : {e}")
        finally:
            # Supprimer en base même si Mistral a échoué
            title = chatbot.title
            chatbot.delete()
            messages.success(request, f"L’agent IA « {title} » a été supprimé avec succès.")
        return redirect("chatbotengine:chatbot_list")

    # Pour plus de sécurité : confirmer avant suppression
    return render(request, "ChatBotEngine/chatbot_confirm_delete.html", {"chatbot": chatbot})




############### HELPER POUR CHAT    ########################

from mistralai import Mistral
import datetime as _dt

def _json_default(o):
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    return str(o)

# --- MINIMAL: séparation agent / conversation ---
from django.conf import settings
from mistralai import Mistral

def _build_agent_tools(instructions):
    tools = []
    if getattr(instructions, "enable_image_tool", False):
        tools.append({"type": "image_generation"})
    if getattr(instructions, "enable_web_search", False):
        tools.append({"type": "web_search"})
    # Librairie documentaire (si dispo)
    try:
        agent_lib_id = get_or_create_agent_library(instructions)
        if agent_lib_id:
            tools.append({"type": "document_library", "library_ids": [agent_lib_id]})
    except Exception as e:
        logger.warning("Agent %s: library Mistral indisponible: %s", instructions.id, e)
    return tools or None



def create_mistral_conversation(agent_id: str, inputs: str):
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    return client.beta.conversations.start(agent_id=agent_id, inputs=inputs)

def append_to_mistral_conversation(conversation_id: str, inputs: str):
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    return client.beta.conversations.append(conversation_id=conversation_id, inputs=inputs)


################# CLONAGE D'UN AGENT #########################

from datetime import timedelta
from django.utils import timezone
import uuid
import logging
from django.conf import settings
from mistralai import Mistral
from .models import AgentInstruction
from ChatBotEngine.utils import _build_agent_directive

logger = logging.getLogger(__name__)



def clone_agent_for_user(parent_agent: AgentInstruction, user) -> AgentInstruction:
    """
    Clone un agent existant pour un utilisateur donné :
    - crée une nouvelle librairie Mistral,
    - crée un agent clone qui référence à la fois la librairie du parent et sa propre librairie.
    - injecte la directive JSON standard dans le clone Mistral.
    """
    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # 1️⃣ Créer une nouvelle librairie Mistral pour le clone
    new_lib = client.beta.libraries.create(
        name=f"lib_clone_{uuid.uuid4()}",
        description=f"Librairie propre au clone de {parent_agent.title}"
    )
    new_lib_id = new_lib.id

    # 2️⃣ Créer localement le clone de l’agent
    clone = AgentInstruction.objects.create(
        source_agent=parent_agent,
        is_temporary=True,
        title=f"{parent_agent.title} (session {user.username})",
        intro_text=parent_agent.intro_text,
        content=parent_agent.content,
        mistral_model=parent_agent.mistral_model,
        temperature=parent_agent.temperature,
        top_p=parent_agent.top_p,
        enable_file_upload=parent_agent.enable_file_upload,
        enable_image_tool=parent_agent.enable_image_tool,
        enable_web_search=parent_agent.enable_web_search,
        owner=user,
        mistral_library_id=new_lib_id,
        expires_at=timezone.now() + timedelta(days=7),
    )

    # 3️⃣ Créer aussi l’agent clone côté Mistral
    parent_lib_id = parent_agent.mistral_library_id
    library_ids = [lid for lid in [parent_lib_id, new_lib_id] if lid]

    try:
        model_name = clone.mistral_model.name if clone.mistral_model_id else "mistral-large-latest"

        # 🧩 Injecter la directive de format JSON
        formatted_instructions = _build_agent_directive(clone.content)

        tools = []
        if library_ids:
            tools.append({"type": "document_library", "library_ids": library_ids})
        if clone.enable_web_search:
            tools.append({"type": "web_search"})
        if clone.enable_image_tool:
            tools.append({"type": "image_generation"})

        agent = client.beta.agents.create(
            model=model_name,
            name=clone.title,
            description=f"Clone de {parent_agent.title} pour {user.username}",
            instructions=formatted_instructions,  # ✅ ici la directive JSON intégrée
            completion_args={
                "temperature": clone.temperature,
                "top_p": clone.top_p,
            },
            tools=tools,
        )

        clone.mistral_agent_id = agent.id
        clone.save(update_fields=["mistral_agent_id"])

        logger.info(f"🌐 Clone Mistral créé : {agent.id} | libs={library_ids}")

    except Exception as e:
        logger.exception(f"❌ Erreur création agent Mistral pour le clone de {parent_agent.id}: {e}")

    return clone



#############################   LANCEMENT DU CHAT SUR UN CLONE     ################################


def clone_and_start_chat(request, parent_agent_id):
    parent_agent = get_object_or_404(AgentInstruction, pk=parent_agent_id)

    # ✅ Clonage
    cloned_agent = clone_agent_for_user(parent_agent, request.user)
    if not cloned_agent:
        messages.error(request, "Échec du clonage de l’agent.")
        return redirect("chatbotengine:chatbot_list")

    logger.info(f"🧬 Agent {parent_agent.id} cloné en {cloned_agent.id} pour {request.user.username}")

    # ✅ Redirection immédiate vers la page de chat du clone
    return redirect("chatbotengine:dynamic_chat_markdown", id=cloned_agent.id)



#################   VUE LANCEMENT DU CHAT, FAIT LE TRI ENTRE LES CLONES ET LES VRAIS


def open_chat(request, agent_id: int):
    """
    Vue pivot : ouvre une session de chat à partir d’un agent.
    Si l’agent autorise l’upload de fichiers, on clone d’abord l’agent
    (et sa librairie), puis on redirige vers le chat du clone.
    Sinon, on ouvre directement le chat sur l’agent d’origine.
    """
    agent = get_object_or_404(AgentInstruction, pk=agent_id)

    # Cas 1 : l’agent permet l’upload → clonage
    if getattr(agent, "enable_file_upload", False):
        try:
            cloned = clone_agent_for_user(agent, request.user)
            logger.info(f"🧬 Clonage agent {agent.id} → {cloned.id} (lib={cloned.mistral_library_id}) pour {request.user.username}")
            return redirect("chatbotengine:dynamic_chat_markdown", id=cloned.id)
        except Exception as e:
            logger.exception("❌ Échec du clonage de l’agent %s : %s", agent.id, e)
            messages.error(request, f"Échec du clonage : {e}")
            return redirect("chatbotengine:chatbot_list")

    # Cas 2 : agent standard → ouverture directe
    return redirect("chatbotengine:dynamic_chat_markdown", id=agent.id)




####################    CHAT avec MARKDOWN      ##########################

from mistralai import Mistral
from django.conf import settings
import json, time, re
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages

from .models import AgentInstruction, Conversation, Message
from core.ai_audit.services import log_ai_call, hash_request, compute_cost_and_impact
from ChatBotEngine.utils import (
    extract_markdown_from_agent_response,
    describe_agent_json_structure,
    extract_files_from_agent_response
)


import logging

from ChatBotEngine.helpers import get_or_create_agent_library
logger = logging.getLogger(__name__)

def dynamic_chat_markdown(request, id):
    conversation_id = request.GET.get("conversation_id")

    if request.method == "GET":
        if conversation_id:
            try:
                conv_obj = Conversation.objects.get(id=conversation_id, owner=request.user)

                # ✅ Cas chatbot supprimé → redirection
                if conv_obj.agent_instruction is None:
                    messages.error(
                        request,
                        "Ce chatbot a été supprimé. Impossible de continuer cette conversation."
                    )
                    return HttpResponseRedirect(reverse("chatbotengine:my_conversations"))

                conv_messages = conv_obj.messages.order_by("created_at")
                chat_history = [
                    {
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at.isoformat(),
                        "image_urls": m.metadata.get("image_url", []) if isinstance(m.metadata, dict) else []
                    }
                    for m in conv_messages
                ]
                request.session["chat_history"] = chat_history
                request.session["conversation_id"] = str(conv_obj.id)

            except Conversation.DoesNotExist:
                request.session.pop("chat_history", None)
                request.session.pop("conversation_id", None)
        else:
            for k in ("agent_id", "chat_history", "conversation_id"):  # agent_id ne sera plus utilisé
                if k in request.session:
                    del request.session[k]
            request.session.modified = True

    # --- Récup config Agent ---
    try:
        instructions = get_object_or_404(AgentInstruction, id=id)
        AGENT_INSTRUCTIONS = instructions.content
        INTRO_TEXT = instructions.intro_text
        AGENT_NAME = instructions.title
        AGENT_MODEL = instructions.mistral_model
        AGENT_TEMPERATURE = instructions.temperature
        AGENT_TOP_P = instructions.top_p
    except AgentInstruction.DoesNotExist:
        AGENT_INSTRUCTIONS = ""
        INTRO_TEXT = ""
        AGENT_NAME = ""
        AGENT_MODEL = None
        AGENT_TEMPERATURE = 1
        AGENT_TOP_P = 0.95

    if request.method == "POST":
        status_for_log = "success"
        latency_ms = 0
        input_tokens = 0
        output_tokens = 0
        total_cost = Decimal("0")
        user_msg_obj = None
        assistant_msg_obj = None
        conv_obj = None
        model_name_for_log = (AGENT_MODEL.name if AGENT_MODEL else "")
        ia_structure_info = None

        try:
            user_prompt = request.POST.get("prompt", "").strip()

            # --- 1) Conversation persistante ---
            conv_id = request.session.get("conversation_id")
            if conv_id:
                try:
                    conv_obj = Conversation.objects.get(id=conv_id, owner=request.user)
                except Conversation.DoesNotExist:
                    conv_obj = None
            if conv_obj is None:
                conv_obj = Conversation.objects.create(
                    owner=request.user,
                    agent_instruction=instructions,
                    agent_name=AGENT_NAME,
                    is_persistent=True,
                    expires_at=None,
                    # mistral_conversation_id: NULL par défaut
                )
                request.session["conversation_id"] = str(conv_obj.id)
                request.session.modified = True

            # --- 2) Historique en session (pour l'UI, inchangé) ---
            chat_history = request.session.get("chat_history", [])
            chat_history.append({"role": "user", "content": user_prompt})
            request.session["chat_history"] = chat_history
            request.session.modified = True

            # --- 3) Message user persisté ---
            user_msg_obj = Message.objects.create(
                conversation=conv_obj,
                role="user",
                content=user_prompt,
                content_hash=hash_request(user_prompt),
                model="",
                tokens_input=0,
                tokens_output=0,
                metadata={},
            )
            conv_obj.set_title_if_empty(user_prompt.splitlines()[0] if user_prompt else "")

            # --- 4) Agent persistant + conversation Mistral ---
            # 4.1 garantir l'existence d'un agent persistant chez Mistral
            ensure_agent_exists_on_mistral(instructions)  # remplit instructions.mistral_agent_id si besoin

            # 4.2 start ou append selon présence de l'ID de conversation Mistral
            t0 = time.perf_counter()
            mistral_conv_id = conv_obj.mistral_conversation_id
            try:
                if mistral_conv_id:
                    conv_response_obj = append_to_mistral_conversation(
                        conversation_id=mistral_conv_id,
                        inputs=user_prompt
                    )
                else:
                    conv_response_obj = create_mistral_conversation(
                        agent_id=instructions.mistral_agent_id,
                        inputs=user_prompt
                    )
                    conv_obj.mistral_conversation_id = conv_response_obj.conversation_id
                    
                    #Pour éviter les time out sur requêtes longues
                    connection.close()
                    
                    conv_obj.save(update_fields=["mistral_conversation_id"])
            except Exception:
                # Fallback robuste : si append échoue (conv expirée/supprimée), on redémarre
                conv_response_obj = create_mistral_conversation(
                    agent_id=instructions.mistral_agent_id,
                    inputs=user_prompt
                )
                conv_obj.mistral_conversation_id = conv_response_obj.conversation_id
                
                #Pour éviter les time out sur requêtes longues
                connection.close()
                
                conv_obj.save(update_fields=["mistral_conversation_id"])

            latency_ms = int((time.perf_counter() - t0) * 1000)
            conv_result = conv_response_obj.dict()

            # --- Extraction texte + images (inchangé) ---
            outputs = conv_result.get("outputs", [])
            message_texts = []
            image_urls = []

            for entry in outputs:
                if entry.get("type") == "message.output":
                    content = entry.get("content", [])

                    if isinstance(content, str):
                        message_texts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                if part.get("type") == "text":
                                    message_texts.append(part.get("text", ""))
                                elif part.get("type") == "tool_file":
                                    # 👉 Extraction de l’image (comportement normal)
                                    file_id = part.get("file_id")
                                    if file_id:
                                        proxy_url = request.build_absolute_uri(
                                            reverse("chatbotengine:mistral_file_proxy", args=[file_id])
                                        )
                                        image_urls.append(proxy_url)


            # --- 4.3) Extraction du texte et validation du format JSON si applicable ---

            raw_message = "".join(message_texts).strip()
            
            # 🔧 Nettoyage : suppression des marqueurs d’image textuels insérés par Mistral
            #raw_message = re.sub(r"\*\*\[Image.*?\]\*\*", "", raw_message, flags=re.IGNORECASE)
            #raw_message = re.sub(r"\[Image.*?\]", "", raw_message, flags=re.IGNORECASE)

            
            # Decomposition du JSON de réponse et caractérisation de ce JSON
            
            message = extract_markdown_from_agent_response(raw_message)
            file_infos = extract_files_from_agent_response(raw_message, request=request)
            ia_structure_info = describe_agent_json_structure(raw_message)


            #try:
                #validated_json = validate_agent_response(raw_message)
            #    message = extract_markdown_from_agent_response(validated_json)
            #    ia_structure_info = "✅ Réponse JSON avec champ main_markdown"
            #except Exception:
            #    message = raw_message
            #    ia_structure_info = "🟢 Réponse texte libre / Markdown direct"



            
            usage = conv_result.get("usage", {})
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
            connector_tokens = int(usage.get("connector_tokens", 0) or 0)
            total_tokens = input_tokens + output_tokens + connector_tokens

            # --- 4bis) Calcul coût et impact via modèle Mistral en BDD ---
            cost_eur, co2_grams, total_tokens = compute_cost_and_impact(
                model_name=AGENT_MODEL.name if AGENT_MODEL else "",
                tokens_input=input_tokens,
                tokens_output=output_tokens + connector_tokens
            )
            total_cost = cost_eur


            # --- 5) Historique assistant (UI) ---
            chat_history.append({
                "role": "assistant",
                "content": message,
                "image_url": image_urls,
                "file_urls": file_infos,
            })
            request.session["chat_history"] = chat_history
            request.session.modified = True

            # --- 6) Message assistant persisté ---
            assistant_msg_obj = Message.objects.create(
                conversation=conv_obj,
                role="assistant",
                content=message or "",
                content_hash=hash_request(message or ""),
                model=model_name_for_log,
                tokens_input=input_tokens,
                tokens_output=output_tokens + connector_tokens,
                metadata={
                    "raw_usage": conv_result.get("usage", {}),
                    "image_url": image_urls
                },
            )

            if not message and not image_urls:
                debug_raw = json.dumps(conv_result, indent=2, ensure_ascii=False, default=_json_default)
                return JsonResponse({
                    "response": None,
                    "image_urls": [],
                    "raw_response": debug_raw,
                    "model_name": model_name_for_log,
                    "total_tokens": total_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens + connector_tokens,
                    "total_cost": float(total_cost),
                    "format": "markdown",
                    "ia_structure_info": ia_structure_info,
                    "file_urls": file_infos,
                },
                json_dumps_params={"ensure_ascii": False},
                content_type="application/json; charset=utf-8")

            return JsonResponse({
                "response": message or None,
                "image_urls": image_urls,
                "model_name": model_name_for_log,
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens + connector_tokens,  # ✅ ajouté pour cohérence
                "total_cost": float(total_cost),
                "format": "markdown",
                "raw_response": json.dumps(conv_result, indent=2, ensure_ascii=False, default=_json_default),
                "ia_structure_info": ia_structure_info,
                "file_urls": file_infos,
            },
            json_dumps_params={"ensure_ascii": False},
            content_type="application/json; charset=utf-8")

        except Exception as e:
            status_for_log = "error"
            import traceback
            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)

        finally:
            try:
                log_ai_call(
                    user=request.user if hasattr(request, "user") and request.user.is_authenticated else None,
                    source_app="ChatBotEngine",
                    source_module="views.dynamic_chat_markdown",
                    provider="mistral",
                    model=model_name_for_log,
                    tokens_input=input_tokens,
                    tokens_output=output_tokens + connector_tokens,
                    request_hash=hash_request((request.POST.get("prompt") or "")),
                    latency_ms=latency_ms,
                    status=status_for_log,
                    metadata={
                        "conversation_id": str(conv_obj.id) if conv_obj else None,
                        "user_message_id": user_msg_obj.id if user_msg_obj else None,
                        "assistant_message_id": assistant_msg_obj.id if assistant_msg_obj else None,
                        "agent_instruction_id": id,
                        "mistral_conversation_id": getattr(conv_obj, "mistral_conversation_id", None),
                    },
                    cost_eur=total_cost,
                )
            except Exception:
                pass

    existing_links = AgentFileLink.objects.filter(agent=instructions).select_related("file").order_by("-id")

    # 🔁 Rafraîchissement opportuniste des statuts "Running"
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    for link in existing_links:
        fa = link.file
        if fa.processing_status not in ("Completed", "Succeeded", "Failed"):
            try:
                resp = client.beta.libraries.documents.get(
                    library_id=instructions.mistral_library_id,
                    document_id=fa.mistral_document_id,
                )
                status = getattr(resp, "processing_status", None) or getattr(resp, "status", "Unknown")
                if status and status != fa.processing_status:
                    fa.processing_status = status
                    fa.save(update_fields=["processing_status"])
            except Exception as e:
                logger.warning(f"Impossible de rafraîchir le statut du fichier {fa.id}: {e}")

    debug_text = None
    if request.user.is_staff:
        agent_id = getattr(instructions, "mistral_agent_id", None)
        library_id = getattr(instructions, "mistral_library_id", None)

        # 🧩 Description structure IA
        raw_text = "\n".join(message_texts).strip() if 'message_texts' in locals() else ""
        ia_structure_info = describe_agent_json_structure(raw_text)

        debug_text = (
            f"🧩 DEBUG — Agent ID : {agent_id or '—'} · "
            f"Library ID : {library_id or '—'} · {ia_structure_info}"
        )


    
    return render(
        request,
        "ChatBotEngine/dynamic_chat_markdown.html",
        {
            "intro_text": INTRO_TEXT,
            "agent_name": AGENT_NAME,
            "row_id": id,
            "chat_history": json.dumps(request.session.get("chat_history", []), ensure_ascii=False),
            "existing_files": [
                {
                    "id": l.id,
                    "name": l.file.original_name or "Fichier sans nom",
                    "status": l.file.processing_status or "Inconnu",
                }
                for l in existing_links
            ],
            "agent_enable_file_upload": getattr(instructions, "enable_file_upload", False),
             # 🧩 Debug temporaire — IDs pour affichage dans le chat
            "debug_text": debug_text,
        },
    )




# FICHIERS DANS LA DEFINITION D'UN AGENT

import logging
from ChatBotEngine.helpers import (
    get_or_create_agent_library,
    remove_docs_from_agent_library,
)
logger = logging.getLogger(__name__)


# ChatBotEngine/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from .models import AgentInstruction, AgentFileLink


def _can_manage_agent_files(user, agent: AgentInstruction) -> bool:
    return user.is_superuser or agent.owner_id == user.id



@require_http_methods(["GET"])
def agent_files(request, agent_id: int):
    agent = get_object_or_404(AgentInstruction, id=agent_id)
    if not _can_manage_agent_files(request.user, agent):
        messages.error(request, "Vous n’êtes pas autorisé à gérer les fichiers de cet agent.")
        return redirect("chatbotengine:my_conversations")  # adapte si besoin

    # Fichiers déjà liés
    links = AgentFileLink.objects.filter(agent=agent).select_related("file")

    # Fichiers éligibles (du propriétaire de l’agent, uploadés & indexés)
    # NB: Mistral renvoie "Completed" (et parfois "Succeeded"); on accepte les deux.
    eligible = FileAsset.objects.filter(
        owner=agent.owner,
        uploaded_to_mistral=True,
        processing_status__in=["Completed", "Succeeded"],
    ).order_by("-created_at")

    ctx = {
        "agent": agent,
        "links": links,
        "eligible_files": eligible,
    }
    return render(request, "ChatBotEngine/agent_files.html", ctx)

# views.py
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from mistralai import Mistral
from mistralai.models import File as MFile  # wrapper SDK
from .models import AgentInstruction, AgentFileLink
from .helpers import get_or_create_agent_library
import logging

logger = logging.getLogger(__name__)

@require_POST
def agent_files_upload(request, agent_id: int):
    agent = get_object_or_404(AgentInstruction, id=agent_id)

    # (Optionnel) autorisation
    if getattr(agent, "owner_id", None) != getattr(request.user, "id", None) and not request.user.is_superuser:
        messages.error(request, "Vous n’êtes pas autorisé à gérer les fichiers de cet agent.")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    f = request.FILES.get("file")
    if not f:
        messages.warning(request, "Aucun fichier sélectionné.")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    # (Optionnel) garde-fous rapides
    if f.size <= 0:
        messages.error(request, "Le fichier est vide.")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    # 1) S’assurer que la librairie existe
    lib_id_before = agent.mistral_library_id
    try:
        get_or_create_agent_library(agent)
    except Exception as e:
        logger.exception("Init library FAILED (agent=%s): %s", agent.id, e)
        messages.error(request, "Impossible d'initialiser la librairie de l’agent.")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    # 2) Upload direct vers la librairie de l’agent (ONE SHOT)
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    try:
        # Attention: .read() charge en mémoire. Suffisant pour un flux simple/unique.
        content_bytes = f.read()
        uploaded = client.beta.libraries.documents.upload(
            library_id=agent.mistral_library_id,
            file=MFile(fileName=f.name, content=content_bytes),
        )
        # Le SDK renvoie un objet document (id, name, status, ...)
        doc_id = getattr(uploaded, "id", None)
        status = getattr(uploaded, "status", None) or getattr(uploaded, "processing_status", "Running")
        if not doc_id:
            raise RuntimeError("Upload Mistral OK mais aucun document_id retourné.")
    except Exception as e:
        logger.exception("Upload vers librairie Mistral échoué (agent=%s): %s", agent.id, e)
        messages.error(request, f"Échec de l’upload vers Mistral : {e}")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    # 3) Persister localement un FileAsset minimal + lien
    fa = FileAsset.objects.create(
        owner=agent.owner,
        original_name=getattr(f, "name", None) or "fichier",
        size_bytes=getattr(f, "size", None) or 0,
        uploaded_to_mistral=True,
        processing_status=status,
        mistral_document_id=doc_id,
    )
    AgentFileLink.objects.get_or_create(agent=agent, file=fa, defaults={"added_by": request.user})

    # 4) Si la lib vient d’être créée ici, patcher l’agent pour lui attacher document_library
    if not lib_id_before and agent.mistral_library_id:
        try:
            update_agent_on_mistral(agent)
            logger.info("Agent %s patched to include document_library %s", agent.id, agent.mistral_library_id)
        except Exception as e:
            logger.warning("Patch agent FAILED (attach library) agent=%s lib=%s err=%s",
                           agent.id, agent.mistral_library_id, e)

    messages.success(request, f"« {f.name} » a été envoyé dans la librairie de l’agent.")
    return redirect("chatbotengine:agent_files", agent_id=agent.id)



@require_http_methods(["POST"])
def agent_files_remove(request, link_id: int):
    link = get_object_or_404(AgentFileLink, id=link_id)
    agent = link.agent
    if not _can_manage_agent_files(request.user, agent):
        messages.error(request, "Vous n’êtes pas autorisé à gérer les fichiers de cet agent.")
        return redirect("chatbotengine:agent_files", agent_id=agent.id)

    # garder la réf doc avant suppression BDD
    fa = link.file
    mistral_doc_id = getattr(fa, "mistral_document_id", None)

    # suppression du lien en base (inchangé)
    link.delete()

    # 🔁 miroir Mistral : retirer de la librairie de l’agent
    if mistral_doc_id:
        try:
            remove_docs_from_agent_library(agent, [mistral_doc_id])
        except Exception as e:
            logger.warning("Mistral remove failed (agent=%s, doc=%s): %s", agent.id, mistral_doc_id, e)

    messages.success(request, "Fichier retiré des ressources de l’agent.")
    return redirect("chatbotengine:agent_files", agent_id=agent.id)




from .models import AgentFileLink

def get_agent_fixed_document_ids(agent) -> list[str]:
    """
    Retourne la liste des IDs de documents Mistral à passer au modèle
    depuis les fichiers 'fixes' rattachés à l'agent.
    """
    links = AgentFileLink.objects.select_related("file").filter(agent=agent)
    doc_ids = []
    for l in links:
        f = l.file
        if f.uploaded_to_mistral and f.mistral_document_id and f.processing_status in ["Completed", "Succeeded"]:
            doc_ids.append(f.mistral_document_id)
    return doc_ids
    
    
    
################        ADMIN          ######################



from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.contrib.auth import get_user_model
from mistralai import Mistral
import logging
from core.models import UserProfile


from .models import AgentInstruction

logger = logging.getLogger(__name__)

def _as_list(result, item_keys=("items", "documents", "data", "results")):
    for k in item_keys:
        v = getattr(result, k, None)
        if v is not None:
            try:
                return list(v)
            except TypeError:
                pass
    if hasattr(result, "model_dump"):
        dumped = result.model_dump()
        for k in item_keys:
            if k in dumped and isinstance(dumped[k], list):
                return dumped[k]
    try:
        return list(result)
    except Exception:
        return []

def _get_attr(d, *names, default=None):
    for n in names:
        val = getattr(d, n, None) if hasattr(d, n) else (d.get(n) if isinstance(d, dict) else None)
        if val is not None:
            return val
    return default

@staff_member_required
def mistral_docs_admin(request):
    """
    Page d’admin: agrège les documents à partir des librairies connues en BDD
    (librairies d’agent +, optionnel, librairies utilisateurs).
    """
    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # 1) Collecter les IDs de librairies d’agent connus en BDD
    agent_lib_ids = list(
        AgentInstruction.objects.exclude(mistral_library_id__isnull=True)
        .exclude(mistral_library_id__exact="")
        .values_list("mistral_library_id", flat=True)
        .distinct()
    )

    # 2) (Optionnel) Ajouter les librairies utilisateurs (propriétaires d’agents)
    include_user_libraries = True  # mets False si tu ne veux pas les inclure
    user_lib_ids = []
    if include_user_libraries:
        owner_ids = (
            AgentInstruction.objects.exclude(owner__isnull=True)
            .values_list("owner_id", flat=True).distinct()
        )
        User = get_user_model()
        for uid in owner_ids:
            try:
                u = User.objects.get(id=uid)
                lib_id = get_or_create_user_library(u)
                if lib_id:
                    user_lib_ids.append(lib_id)
            except Exception as e:
                logger.warning("Impossible d'obtenir la library user (user=%s): %s", uid, e)

    library_ids = list(dict.fromkeys(agent_lib_ids + user_lib_ids))  # unique & stable order

    # 3) Pour chaque library_id, lister ses documents et agréger
    docs_index = {}
    for lib_id in library_ids:
        page = 0
        while True:
            try:
                r = client.beta.libraries.documents.list(library_id=lib_id, page=page, page_size=200)
            except Exception as e:
                logger.warning("Erreur list docs (library_id=%s, page=%s): %s", lib_id, page, e)
                break

            items = _as_list(r)
            if not items:
                break

            for it in items:
                d_id   = _get_attr(it, "id", "document_id", "uuid")
                fname  = _get_attr(it, "filename", "name", "title")
                status = _get_attr(it, "status", "processing_status")
                size   = _get_attr(it, "size", "file_size", "bytes")
                ctime  = _get_attr(it, "created_at", "uploaded_at", "ingested_at")
                if not d_id:
                    continue
                entry = docs_index.setdefault(d_id, {
                    "id": d_id,
                    "filename": fname,
                    "status": status,
                    "size": size,
                    "created_at": ctime,
                    "ref_agents": 0,
                    "ref_users": 0,
                })
                # métas: première valeur non nulle
                if not entry["filename"] and fname: entry["filename"] = fname
                if not entry["status"] and status: entry["status"] = status
                if not entry["size"] and size: entry["size"] = size
                if not entry["created_at"] and ctime: entry["created_at"] = ctime

                # classer agent vs user selon la provenance
                if lib_id in agent_lib_ids:
                    entry["ref_agents"] += 1
                else:
                    entry["ref_users"] += 1

            if len(items) < 200:
                break
            page += 1

    # 4) Liste triée
    docs = list(docs_index.values())
    for d in docs:
        d["ref_total"] = (d["ref_agents"] or 0) + (d["ref_users"] or 0)

    sort = request.GET.get("sort", "-ref_total")
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    try:
        docs.sort(key=lambda x: (x.get(key) or 0), reverse=reverse)
    except Exception:
        docs.sort(key=lambda x: (x.get("ref_total") or 0), reverse=True)

    return render(request, "ChatBotEngine/admin_mistral_docs.html", {
        "docs": docs,
        "sort": sort,
        "total_docs": len(docs),
    })


from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.conf import settings
from mistralai import Mistral
from core.models import UserProfile
from .models import AgentInstruction
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def admin_list_libraries(request):
    """
    Vue admin listant toutes les librairies Mistral avec leur date de création,
    leurs agents / utilisateurs associés, et un lien vers la page détail.
    """
    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # 1️⃣ Récupération de toutes les librairies via l’API (SDK 1.9.10 → resp.data)
    try:
        resp = client.beta.libraries.list()
        libraries = list(getattr(resp, "data", []) or [])
    except Exception as e:
        messages.error(request, f"Impossible de lister les librairies Mistral : {e}")
        libraries = []

    # 2️⃣ Associer les agents locaux par library_id
    agent_by_lib = {
        lib_id: agent
        for (lib_id, agent) in AgentInstruction.objects
            .exclude(mistral_library_id__isnull=True)
            .exclude(mistral_library_id="")
            .values_list("mistral_library_id", "id")
    }
    agent_objs = AgentInstruction.objects.filter(id__in=list(agent_by_lib.values()))
    agent_map = {a.id: a for a in agent_objs}
    agent_by_lib = {k: agent_map.get(v) for k, v in agent_by_lib.items()}

    # 3️⃣ Associer les profils utilisateurs (UserProfile)
    profiles = (
        UserProfile.objects
        .select_related("user")
        .exclude(mistral_library_id__isnull=True)
        .exclude(mistral_library_id="")
        .values("mistral_library_id", "user__id", "user__username", "user__email")
    )
    user_by_lib = {
        row["mistral_library_id"]: {
            "id": row["user__id"],
            "username": row["user__username"],
            "email": row["user__email"],
        }
        for row in profiles
    }

    # 4️⃣ Construire les lignes à afficher
    rows = []
    for lib in libraries:
        lib_id = getattr(lib, "id", None)
        if not lib_id:
            continue

        rows.append({
            "id": lib_id,
            "name": getattr(lib, "name", "—"),
            "description": getattr(lib, "description", ""),
            "created_at": getattr(lib, "created_at", None),
            "agent": agent_by_lib.get(lib_id),
            "user": user_by_lib.get(lib_id),
        })

    # 5️⃣ Tri par date décroissante
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)

    # 6️⃣ Rendu du template
    return render(request, "ChatBotEngine/admin_libraries.html", {
        "rows": rows,
        "with_counts": "with_counts" in request.GET,
    })


@staff_member_required
def admin_delete_library(request, lib_id: str):
    """
    Supprime une librairie Mistral. Bloqué si un agent local la référence encore.
    """
    # Si encore référencée par un agent, on bloque par sécurité
    linked = AgentInstruction.objects.filter(mistral_library_id=lib_id).first()
    if linked:
        messages.error(
            request,
            f"Librairie {lib_id} référencée par l’agent #{linked.id} « {linked.title} ». "
            "Détache-la d’abord (ou supprime l’agent) avant de supprimer la librairie."
        )
        return redirect(reverse("chatbotengine:admin_list_libraries"))

    if request.method != "POST":
        messages.error(request, "Méthode non autorisée.")
        return redirect(reverse("chatbotengine:admin_list_libraries"))

    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    try:
        # Endpoint documenté : DELETE /v1/libraries/{library_id}
        client.beta.libraries.delete(library_id=lib_id)
        messages.success(request, f"Librairie {lib_id} supprimée côté Mistral.")
    except Exception as e:
        messages.error(request, f"Échec de la suppression de {lib_id} : {e}")

    return redirect(reverse("chatbotengine:admin_list_libraries"))



#### CONTENU D'UNE LIBRAIRIE

@staff_member_required
def admin_library_detail(request):
    """
    Affiche les détails d’une librairie Mistral spécifique,
    avec liste des documents (SDK 1.9.10).
    Les métadonnées de base sont passées en GET (Option B).
    """
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    lib_id = request.GET.get("lib_id")
    name = request.GET.get("name") or "—"
    desc = request.GET.get("desc") or ""
    created = request.GET.get("created")

    docs = []
    total_docs = 0

    if not lib_id:
        messages.error(request, "Aucun ID de librairie spécifié.")
        return redirect("chatbotengine:admin_list_libraries")

    try:
        resp = client.beta.libraries.documents.list(library_id=lib_id)
        docs = list(getattr(resp, "data", []) or getattr(resp, "documents", []) or [])
        total_docs = len(docs)
    except Exception as e:
        logger.warning("Impossible de lister les documents de %s : %s", lib_id, e)
        messages.error(request, f"Impossible de récupérer les documents : {e}")

    return render(request, "ChatBotEngine/admin_library_detail.html", {
        "lib_id": lib_id,
        "name": name,
        "desc": desc,
        "created": created,
        "docs": docs,
        "total_docs": total_docs,
    })





#################    POUR LA SYNCHRO DES AGENTS ENTRE LE BACKEND ET MISTRAL    ##################


# --- Admin : liste des agents Mistral et correspondance backend ---
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.http import urlencode
from mistralai import Mistral
import requests

_MISTRAL_BASE = "https://api.mistral.ai/v1"

def _http_headers():
    return {"Authorization": f"Bearer {settings.MISTRAL_API_KEY}", "Content-Type": "application/json"}

def _list_mistral_agents_via_sdk(client, page_size=200):
    """Essaie via SDK (si dispo). Retourne une liste de dict homogènes."""
    agents = []
    page = 0
    while True:
        try:
            res = client.beta.agents.list(page=page, page_size=page_size)  # SDK récent
        except Exception:
            return None  # on laissera le fallback HTTP gérer
        items = _as_list(res)  # tu as déjà _as_list dans ce fichier plus haut
        if not items:
            break
        for a in items:
            agents.append({
                "id": getattr(a, "id", None) or getattr(a, "agent_id", None) or (a.get("id") if isinstance(a, dict) else None),
                "name": getattr(a, "name", None) if not isinstance(a, dict) else a.get("name"),
                "model": getattr(a, "model", None) if not isinstance(a, dict) else a.get("model"),
                "description": getattr(a, "description", None) if not isinstance(a, dict) else a.get("description"),
                "created_at": getattr(a, "created_at", None) if not isinstance(a, dict) else a.get("created_at"),
                "updated_at": getattr(a, "updated_at", None) if not isinstance(a, dict) else a.get("updated_at"),
            })
        if len(items) < page_size:
            break
        page += 1
    return agents

def _list_mistral_agents_via_http(page_size=200, max_pages=100):
    """Fallback HTTP si le SDK n’expose pas list()."""
    agents = []
    session = requests.Session()
    session.headers.update(_http_headers())

    # L’API publique ne documente pas toujours la pagination ; on boucle prudemment.
    # On tente /v1/agents?limit=&page= ; ajuste si besoin selon ta version.
    for page in range(max_pages):
        params = {"limit": page_size, "page": page}
        r = session.get(f"{_MISTRAL_BASE}/agents", params=params, timeout=30)
        if r.status_code == 404:
            # autre schéma : pas de pagination → un seul retour
            r = session.get(f"{_MISTRAL_BASE}/agents", timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") or data.get("items") or data.get("results") or data
        if not isinstance(items, list):
            items = []
        for a in items:
            agents.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "model": a.get("model"),
                "description": a.get("description"),
                "created_at": a.get("created_at"),
                "updated_at": a.get("updated_at"),
            })
        if len(items) < page_size:
            break
    return agents

@staff_member_required
def mistral_agents_admin(request):
    q = (request.GET.get("q") or "").strip().lower()
    sort = request.GET.get("sort") or "-linked"  # linked d’abord par défaut

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    agents = _list_mistral_agents_via_sdk(client)
    if agents is None:
        agents = _list_mistral_agents_via_http()

    # Index des liens backend : {mistral_agent_id: (id, title, owner)}
    linked_map = {
        mid: (aid, title, owner_email)
        for (mid, aid, title, owner_email) in AgentInstruction.objects
            .exclude(mistral_agent_id__isnull=True)
            .exclude(mistral_agent_id__exact="")
            .values_list("mistral_agent_id", "id", "title", "owner__email")
    }

    # Enrichir + filtrer
    rows = []
    for a in agents:
        aid = a.get("id")
        linked = aid in linked_map
        backend_id, backend_title, owner_email = (linked_map.get(aid) or (None, None, None))
        row = {
            "id": aid,
            "name": a.get("name") or "",
            "model": a.get("model") or "",
            "description": a.get("description") or "",
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
            "linked": linked,
            "backend_id": backend_id,
            "backend_title": backend_title,
            "owner_email": owner_email,
        }
        if q:
            hay = " ".join([str(v or "") for v in [row["id"], row["name"], row["model"], row["backend_title"], row["owner_email"]]]).lower()
            if q not in hay:
                continue
        rows.append(row)

    # Tri
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    if key == "linked":
        rows.sort(key=lambda r: (not r["linked"], r["name"]), reverse=reverse)  # linked True avant False
    else:
        rows.sort(key=lambda r: (r.get(key) or ""), reverse=reverse)

    # Compteurs
    total = len(rows)
    total_linked = sum(1 for r in rows if r["linked"])

    # Rebuild query sans sort pour les liens de tri
    def qstr(**kwargs):
        base = {}
        if q:
            base["q"] = q
        base.update(kwargs)
        return "?" + urlencode(base)

    return render(request, "ChatBotEngine/admin_mistral_agents.html", {
        "rows": rows,
        "total": total,
        "total_linked": total_linked,
        "q": q,
        "sort": sort,
        "qstr": qstr,
    })


### SUPPRESSION AGENT COTE MISTRAL    ######


from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import redirect

@staff_member_required
@require_POST
def mistral_agent_delete(request):
    agent_id = (request.POST.get("agent_id") or "").strip()
    if not agent_id:
        messages.error(request, "Agent Mistral introuvable.")
        return redirect("chatbotengine:mistral_agents_admin")

    # Option: prévenir si lié en BDD (on autorise quand même la suppression côté Mistral)
    linked = AgentInstruction.objects.filter(mistral_agent_id=agent_id).exists()

    try:
        r = requests.delete(f"{_MISTRAL_BASE}/agents/{agent_id}", headers=_http_headers(), timeout=20)
        # Best effort : 2xx/404 -> ok
        if r.status_code not in (200, 202, 204, 404):
            r.raise_for_status()
        if linked:
            messages.warning(request, "Agent supprimé côté Mistral. Des agents backend y étaient liés ; ils seront recréés à l'usage.")
        else:
            messages.success(request, "Agent supprimé côté Mistral.")
    except Exception as e:
        messages.error(request, f"Échec suppression Mistral : {e}")

    # Revenir à la liste (garde q/sort si besoin: utiliser HTTP Referer si présent)
    return redirect(request.META.get("HTTP_REFERER", "chatbotengine:mistral_agents_admin"))
    
    
    
    ################    POUR LES FICHIERS DANS LES CONVERSATIONS      ################
    
from django.http import JsonResponse
from django.conf import settings
from mistralai import Mistral
import logging

logger = logging.getLogger(__name__)


def get_file_status(request, file_id):
    """
    Retourne le statut de processing d’un fichier Mistral.
    Si le statut est en cours, tente de rafraîchir depuis Mistral.
    """
    try:
        file_asset = FileAsset.objects.get(id=file_id, owner=request.user)
    except FileAsset.DoesNotExist:
        return JsonResponse({"success": False, "error": "Fichier introuvable ou non autorisé."}, status=404)

    # Si déjà complété/success/failed → inutile d’appeler l’API Mistral
    if file_asset.processing_status in ("Completed", "Succeeded", "Failed"):
        return JsonResponse({"success": True, "status": file_asset.processing_status})

    # 🔍 Trouver la librairie via AgentFileLink
    link = AgentFileLink.objects.filter(file=file_asset).select_related("agent").first()
    if not link or not link.agent or not link.agent.mistral_library_id:
        return JsonResponse({
            "success": False,
            "status": file_asset.processing_status,
            "error": "Aucun agent lié à ce fichier."
        }, status=400)

    # Interroger Mistral
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    try:
        resp = client.beta.libraries.documents.get(
            library_id=link.agent.mistral_library_id,
            document_id=file_asset.mistral_document_id,
        )
        status = getattr(resp, "processing_status", None) or getattr(resp, "status", "Unknown")

        if status and status != file_asset.processing_status:
            file_asset.processing_status = status
            file_asset.save(update_fields=["processing_status"])
    except Exception as e:
        logger.warning("Erreur de rafraîchissement du statut du fichier %s: %s", file_id, e)
        return JsonResponse({"success": False, "status": file_asset.processing_status, "error": str(e)}, status=500)

    return JsonResponse({"success": True, "status": file_asset.processing_status})




from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from mistralai import Mistral
from mistralai.models import File as MFile
from .models import AgentInstruction, Conversation, AgentFileLink
from .helpers import get_or_create_agent_library
import logging

logger = logging.getLogger(__name__)


def chat_upload_file(request, agent_id):
    """
    Upload d’un fichier vers la librairie Mistral de l’agent associé au chat en cours.
    Compatible avec un identifiant d’agent numérique (non UUID).
    Retourne une réponse JSON exploitable côté front.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"}, status=405)

    # 1️⃣ Vérification de l’agent
    agent = get_object_or_404(AgentInstruction, id=agent_id)

    # 2️⃣ Autorisation (propriétaire ou superuser)
    if request.user != agent.owner and not request.user.is_superuser:
        return JsonResponse({"success": False, "error": "Non autorisé"}, status=403)

    # 3️⃣ Vérification du fichier reçu
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"success": False, "error": "Aucun fichier reçu"}, status=400)

    if f.size <= 0:
        return JsonResponse({"success": False, "error": "Le fichier est vide"}, status=400)

    # 4️⃣ S’assurer que la librairie Mistral existe
    try:
        get_or_create_agent_library(agent)
    except Exception as e:
        logger.exception("Init library FAILED (agent=%s): %s", agent.id, e)
        return JsonResponse(
            {"success": False, "error": "Impossible d'initialiser la librairie de l’agent."},
            status=500
        )

    # 5️⃣ Upload vers la librairie Mistral
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    try:
        content_bytes = f.read()
        uploaded = client.beta.libraries.documents.upload(
            library_id=agent.mistral_library_id,
            file=MFile(fileName=f.name, content=content_bytes),
        )
        doc_id = getattr(uploaded, "id", None)
        status = getattr(uploaded, "status", None) or getattr(uploaded, "processing_status", "Running")
        if not doc_id:
            raise RuntimeError("Upload Mistral OK mais aucun document_id retourné.")
    except Exception as e:
        logger.exception("Upload vers Mistral échoué (agent=%s): %s", agent.id, e)
        return JsonResponse(
            {"success": False, "error": f"Échec de l’upload vers Mistral : {e}"},
            status=500
        )

    # 6️⃣ Création du FileAsset local et lien avec l’agent
    fa = FileAsset.objects.create(
        owner=request.user,
        original_name=getattr(f, "name", None) or "fichier",
        size_bytes=getattr(f, "size", None) or 0,
        uploaded_to_mistral=True,
        processing_status=status,
        mistral_document_id=doc_id,
    )

    AgentFileLink.objects.get_or_create(
        agent=agent,
        file=fa,
        defaults={"added_by": request.user},
    )

    logger.info(
        "Chat upload: fichier %s ajouté à la librairie %s (status=%s)",
        f.name,
        agent.mistral_library_id,
        status
    )

    # 7️⃣ Réponse JSON immédiate pour le front
    return JsonResponse({
        "success": True,
        "file_id": fa.id,
        "filename": f.name,
        "status": status,
    })


# ChatBotEngine/views.py

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import AgentFileLink
from .helpers import remove_docs_from_agent_library
import logging

logger = logging.getLogger(__name__)

def chat_file_remove(request, link_id: int):
    """
    Supprime un fichier depuis le chat (JSON).
    Reprend la logique de agent_files_remove mais renvoie un JsonResponse.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"}, status=405)

    link = get_object_or_404(AgentFileLink, id=link_id)
    agent = link.agent

    if not (request.user.is_superuser or agent.owner_id == request.user.id):
        return JsonResponse({"success": False, "error": "Non autorisé"}, status=403)

    fa = link.file
    mistral_doc_id = getattr(fa, "mistral_document_id", None)

    # Suppression du lien
    link.delete()

    # 🔁 Suppression côté Mistral
    if mistral_doc_id:
        try:
            remove_docs_from_agent_library(agent, [mistral_doc_id])
        except Exception as e:
            logger.warning("Mistral remove failed (agent=%s, doc=%s): %s", agent.id, mistral_doc_id, e)

    # Si plus aucun lien → suppression du FileAsset
    if not AgentFileLink.objects.filter(file=fa).exists():
        fa.delete()

    return JsonResponse({"success": True})


    
