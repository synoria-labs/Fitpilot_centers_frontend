"""Service layer for the WhatsApp chat feature (conversations, messages, sending).

Talks to the backend GraphQL API over the shared httpx client. Realtime updates are
handled separately by the WebSocket subscription client (graphql/ws_client.py).
"""
from typing import List, Optional, Dict, Any

from ..core.logging import get_logger
from ..models.chat import ChatConversation, ChatMessage

logger = get_logger(__name__)

_MESSAGE_FIELDS = """
    id
    conversationId
    contactId
    direction
    messageType
    textContent
    timestamp
    waMessageId
    mediaUrl
"""

CONVERSATIONS_QUERY = """
    query GetConversations($limit: Int = 50, $offset: Int! = 0, $search: String) {
        conversations(limit: $limit, offset: $offset, search: $search) {
            id
            status
            lastActivity
            unreadCount
            contact { id waId phoneNumber name profileName }
            lastMessage { %s }
        }
    }
""" % _MESSAGE_FIELDS

MESSAGES_QUERY = """
    query GetMessages($conversationId: Int!, $limit: Int! = 50, $offset: Int! = 0) {
        conversationMessages(conversationId: $conversationId, limit: $limit, offset: $offset) {
            %s
        }
    }
""" % _MESSAGE_FIELDS

SEND_MUTATION = """
    mutation SendText($input: SendTextMessageInput!) {
        sendTextMessage(input: $input) {
            success
            error
            message { %s }
        }
    }
""" % _MESSAGE_FIELDS


class WhatsAppChatService:
    """GraphQL operations for the WhatsApp chat UI."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_conversations(
        self, limit: int = 50, offset: int = 0, search: Optional[str] = None
    ) -> List[ChatConversation]:
        variables = {"limit": limit, "offset": offset, "search": search}
        try:
            result = await self.client.execute(CONVERSATIONS_QUERY, variables)
            items = (result or {}).get("conversations") or []
            return [ChatConversation.from_dict(item) for item in items]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching conversations: %s", exc)
            return []

    async def get_messages(
        self, conversation_id: int, limit: int = 50, offset: int = 0
    ) -> List[ChatMessage]:
        variables = {"conversationId": conversation_id, "limit": limit, "offset": offset}
        try:
            result = await self.client.execute(MESSAGES_QUERY, variables)
            items = (result or {}).get("conversationMessages") or []
            return [ChatMessage.from_dict(item) for item in items]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching messages for conversation %s: %s", conversation_id, exc)
            return []

    async def send_text_message(
        self,
        conversation_id: Optional[int] = None,
        wa_id: Optional[str] = None,
        text: str = "",
    ) -> Dict[str, Any]:
        input_payload: Dict[str, Any] = {"text": text}
        if conversation_id is not None:
            input_payload["conversationId"] = conversation_id
        if wa_id:
            input_payload["waId"] = wa_id

        try:
            result = await self.client.execute(SEND_MUTATION, {"input": input_payload})
            payload = (result or {}).get("sendTextMessage") or {}
            msg = payload.get("message")
            return {
                "success": bool(payload.get("success")),
                "error": payload.get("error"),
                "message": ChatMessage.from_dict(msg) if msg else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending text message: %s", exc)
            return {"success": False, "error": str(exc), "message": None}
