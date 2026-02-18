from django.urls import path
from . import views
from .views import my_conversations


app_name = "chatbotengine"

urlpatterns = [
    path("mes-conversations/", my_conversations, name="my_conversations"),
    path("mes-conversations/<uuid:pk>/delete/", views.delete_conversation, name="delete_conversation"),
    path("chatbots/", views.chatbot_list, name="chatbot_list"),
    path("chatbots/creation/", views.create_chatbot, name="create_chatbot"),
    path("chatbots/<int:pk>/modification/", views.update_chatbot, name="update_chatbot"),
    path("chatbots/<int:pk>/delete/", views.delete_chatbot, name="delete_chatbot"),
    path("chat_markdown/<int:id>/", views.dynamic_chat_markdown, name="dynamic_chat_markdown"),
    
    # POUR LES IMAGES
    path("mistral_file/<str:file_id>/", views.mistral_file_proxy, name="mistral_file_proxy"),
    
    # FICHIERS ATTACHES AU NIVEAU AGENT
    path("agents/<int:agent_id>/files/", views.agent_files, name="agent_files"),
    path("agents/<int:agent_id>/files/upload", views.agent_files_upload, name="agent_files_upload"),
    path("agents/files/<int:link_id>/remove/", views.agent_files_remove, name="agent_files_remove"),

    # DEMARRAGE DISCUSSION SUR UN CLONE
    path("chatbots/<int:parent_agent_id>/clone_and_start/", views.clone_and_start_chat, name="clone_and_start_chat"),
    
    # DEMARRAGE DISCUSSION SUR UN CLONE OU UN AUTRE -> URL PIVOT
    path("chatbots/<int:agent_id>/open/", views.open_chat, name="open_chat"),


    # FICHIERS DANS LE CHAT
    path("file_status/<int:file_id>/", views.get_file_status, name="chat_get_file_status"),
    path("upload/<int:agent_id>/", views.chat_upload_file, name="chat_upload_file"),
    path("file_remove/<int:link_id>/", views.chat_file_remove, name="chat_file_remove"),


    # ADMIN
    path("admin/mistral-docs/", views.mistral_docs_admin, name="mistral_docs_admin"),
    path("admin/mistral/agents/", views.mistral_agents_admin, name="mistral_agents_admin"),
    path("admin/mistral/agents/delete/", views.mistral_agent_delete, name="mistral_agent_delete"),
    path("admin/libraries/", views.admin_list_libraries, name="admin_list_libraries"),
    path("admin/libraries/<str:lib_id>/delete", views.admin_delete_library, name="admin_delete_library"),
    path("admin/libraries/detail/", views.admin_library_detail, name="admin_library_detail"),


]
