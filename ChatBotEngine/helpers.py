from django.conf import settings
from mistralai import Mistral

def get_or_create_agent_library(agent) -> str:
    """
    Retourne l'ID de la librairie Mistral dédiée à l'agent.
    La crée si absente, puis la stocke dans agent.mistral_library_id.
    """
    if agent.mistral_library_id:
        return agent.mistral_library_id

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # Nom lisible (éviter les noms vides)
    title = (agent.title or "").strip() or f"agent-{agent.id}"
    lib = client.beta.libraries.create(
        name=f"agent-{agent.id}-{title[:40]}",
        description=f"Library for agent {agent.id} ({title})"
    )
    agent.mistral_library_id = lib.id
    agent.save(update_fields=["mistral_library_id"])
    return lib.id


from django.conf import settings
from mistralai import Mistral
import logging

logger = logging.getLogger(__name__)

def remove_docs_from_agent_library(agent, document_ids: list[str]) -> None:
    """Supprime des documents d'une librairie EXISTANTE de l'agent, sans création implicite."""
    if not document_ids:
        return

    lib_id = getattr(agent, "mistral_library_id", None)
    if not lib_id:
        logger.warning("remove_docs: agent %s n'a pas de librairie attachée, skip", getattr(agent, "id", None))
        return

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    # Option A (la plus robuste) : DELETE unitaire pour chaque document
    for did in document_ids:
        if not did:
            continue
        try:
            client.beta.libraries.documents.delete(library_id=lib_id, document_id=did)
        except Exception as e:
            logger.warning("remove_docs: échec suppression doc=%s dans lib=%s (agent=%s): %s",
                           did, lib_id, getattr(agent, "id", None), e)

    # Option B (si tu sais que ton SDK supporte vraiment le batch 'remove')
    # try:
    #     client.beta.libraries.documents.remove(library_id=lib_id, document_ids=document_ids)
    # except Exception as e:
    #     logger.warning("remove_docs batch failed (lib=%s, docs=%s): %s", lib_id, document_ids, e)

