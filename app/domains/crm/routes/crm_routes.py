"""
CRM domain routes.

Handles client management, chat/messaging, and support tickets.

Currently served by:
- admin_bp: chat_support, admin_send_chat_message, mark_chat_read, chat, send_chat_message
- accountant_bp: add_client, search_clients
- superadmin_bp: chat_dashboard, chat_data, send_chat_reply, mark_message_read, mark_all_read
- public_chat_bp: support_chat, send_message, check_messages

The public_chat routes have been copied to this domain.
Other CRM routes will be migrated incrementally.
"""
from flask import Blueprint

crm_bp = Blueprint('crm', __name__, url_prefix='/crm')
