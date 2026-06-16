"""Service layer for the WhatsApp chat feature (conversations, messages, sending).

Talks to the backend GraphQL API over the shared httpx client. Realtime updates are
handled separately by the WebSocket subscription client (graphql/ws_client.py).
"""
from typing import List, Optional, Dict, Any

from ..core.logging import get_logger
from ..models.chat import ChatConversation, ChatMessage

logger = get_logger(__name__)

# Shared page size for the conversation list (infinite scroll).
PAGE_SIZE = 40

_MESSAGE_FIELDS = """
    id
    conversationId
    contactId
    direction
    messageType
    textContent
    timestamp
    waMessageId
    contextMessageId
    mediaUrl
    media {
        id
        mediaType
        mimeType
        filename
        caption
        fileSize
        mediaUrl
        downloaded
        downloadFailed
    }
"""

_CONTACT_FIELDS_WITH_MEMBERSHIP = """
    id
    waId
    phoneNumber
    name
    profileName
    memberId
    memberName
    memberMembership {
        status
        remainingDays
    }
"""

_CONTACT_FIELDS_WITH_MEMBER = """
    id
    waId
    phoneNumber
    name
    profileName
    memberId
    memberName
"""

_CONTACT_FIELDS_BASIC = """
    id
    waId
    phoneNumber
    name
    profileName
"""

CONVERSATIONS_QUERY = """
    query GetConversations($limit: Int = 50, $offset: Int! = 0, $search: String) {
        conversations(limit: $limit, offset: $offset, search: $search) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_WITH_MEMBERSHIP, _MESSAGE_FIELDS)

CONVERSATIONS_MEMBER_QUERY = """
    query GetConversations($limit: Int = 50, $offset: Int! = 0, $search: String) {
        conversations(limit: $limit, offset: $offset, search: $search) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_WITH_MEMBER, _MESSAGE_FIELDS)

CONVERSATIONS_COMPAT_QUERY = """
    query GetConversations($limit: Int = 50, $offset: Int! = 0, $search: String) {
        conversations(limit: $limit, offset: $offset, search: $search) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_BASIC, _MESSAGE_FIELDS)

CONVERSATION_QUERY = """
    query GetConversation($id: Int!) {
        conversation(id: $id) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_WITH_MEMBERSHIP, _MESSAGE_FIELDS)

CONVERSATION_MEMBER_QUERY = """
    query GetConversation($id: Int!) {
        conversation(id: $id) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_WITH_MEMBER, _MESSAGE_FIELDS)

CONVERSATION_COMPAT_QUERY = """
    query GetConversation($id: Int!) {
        conversation(id: $id) {
            id
            status
            lastActivity
            unreadCount
            botEnabled
            contact { %s }
            lastMessage { %s }
        }
    }
""" % (_CONTACT_FIELDS_BASIC, _MESSAGE_FIELDS)

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

SEND_MEDIA_MUTATION = """
    mutation SendMedia($input: SendMediaMessageInput!, $file: Upload!) {
        sendMediaMessage(input: $input, file: $file) {
            success
            error
            message { %s }
        }
    }
""" % _MESSAGE_FIELDS

RETRY_MEDIA_MUTATION = """
    mutation RetryMedia($messageId: Int!) {
        retryMediaDownload(messageId: $messageId) {
            success
            error
            message { %s }
        }
    }
""" % _MESSAGE_FIELDS

SEND_REACTION_MUTATION = """
    mutation SendReaction($input: SendReactionInput!) {
        sendReaction(input: $input) {
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
        self._contact_schema_level = 0

    async def _execute_with_contact_fallback(
        self,
        queries: tuple[str, str, str],
        variables: dict,
        operation_name: str,
    ) -> Optional[dict]:
        level_names = ("membership", "member", "basic")
        for level in range(self._contact_schema_level, len(queries)):
            result = await self.client.execute(queries[level], variables)
            if result is not None:
                if level != self._contact_schema_level:
                    logger.warning(
                        "%s query using %s contact fields after fallback",
                        operation_name,
                        level_names[level],
                    )
                self._contact_schema_level = level
                return result

            logger.warning(
                "%s query with %s contact fields failed; trying fallback",
                operation_name,
                level_names[level],
            )

        return None

    async def get_conversations(
        self, limit: int = PAGE_SIZE, offset: int = 0, search: Optional[str] = None
    ) -> List[ChatConversation]:
        variables = {"limit": limit, "offset": offset, "search": search}
        try:
            result = await self._execute_with_contact_fallback(
                (
                    CONVERSATIONS_QUERY,
                    CONVERSATIONS_MEMBER_QUERY,
                    CONVERSATIONS_COMPAT_QUERY,
                ),
                variables,
                "Conversation",
            )
            items = (result or {}).get("conversations") or []
            return [ChatConversation.from_dict(item) for item in items]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching conversations: %s", exc)
            return []

    async def get_conversation(
        self, conversation_id: int
    ) -> Optional[ChatConversation]:
        """Fetch a single conversation enriched like the list (incremental inserts)."""
        variables = {"id": conversation_id}
        try:
            result = await self._execute_with_contact_fallback(
                (
                    CONVERSATION_QUERY,
                    CONVERSATION_MEMBER_QUERY,
                    CONVERSATION_COMPAT_QUERY,
                ),
                variables,
                "Single conversation",
            )
            item = (result or {}).get("conversation")
            return ChatConversation.from_dict(item) if item else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching conversation %s: %s", conversation_id, exc)
            return None

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

    async def send_media_message(
        self,
        conversation_id: Optional[int] = None,
        wa_id: Optional[str] = None,
        file_path: str = "",
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an attachment via the multipart GraphQL mutation."""
        input_payload: Dict[str, Any] = {}
        if conversation_id is not None:
            input_payload["conversationId"] = conversation_id
        if wa_id:
            input_payload["waId"] = wa_id
        if caption:
            input_payload["caption"] = caption

        try:
            result = await self.client.execute_multipart(
                SEND_MEDIA_MUTATION,
                {"input": input_payload},
                file_path=file_path,
                file_variable="file",
            )
            if result is None:
                error = getattr(self.client, "last_error", None)
                return {"success": False, "error": error or "Error al subir el archivo.", "message": None}
            payload = result.get("sendMediaMessage") or {}
            msg = payload.get("message")
            return {
                "success": bool(payload.get("success")),
                "error": payload.get("error"),
                "message": ChatMessage.from_dict(msg) if msg else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending media message: %s", exc)
            return {"success": False, "error": str(exc), "message": None}

    async def set_conversation_bot_enabled(
        self, conversation_id: int, enabled: bool
    ) -> Dict[str, Any]:
        """Enable/disable the WhatsApp bot for one conversation (robot button)."""
        mutation = """
            mutation SetBot($conversationId: Int!, $enabled: Boolean!) {
                setConversationBotEnabled(conversationId: $conversationId, enabled: $enabled) {
                    id
                    botEnabled
                }
            }
        """
        try:
            result = await self.client.execute(
                mutation, {"conversationId": conversation_id, "enabled": enabled}
            )
            payload = (result or {}).get("setConversationBotEnabled") or {}
            return {
                "success": bool(payload),
                "bot_enabled": bool(payload.get("botEnabled", enabled)),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error toggling conversation bot: %s", exc)
            return {"success": False, "error": str(exc)}

    async def send_reaction(
        self,
        conversation_id: Optional[int],
        message_id: str,
        emoji: str,
    ) -> Dict[str, Any]:
        """React to a message (emoji="" removes the reaction). ``message_id`` is the
        target's wa_message_id."""
        input_payload: Dict[str, Any] = {"messageId": message_id, "emoji": emoji}
        if conversation_id is not None:
            input_payload["conversationId"] = conversation_id
        try:
            result = await self.client.execute(
                SEND_REACTION_MUTATION, {"input": input_payload}
            )
            payload = (result or {}).get("sendReaction") or {}
            msg = payload.get("message")
            return {
                "success": bool(payload.get("success")),
                "error": payload.get("error"),
                "message": ChatMessage.from_dict(msg) if msg else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error sending reaction: %s", exc)
            return {"success": False, "error": str(exc), "message": None}

    async def retry_media_download(self, message_id: int) -> Dict[str, Any]:
        """Ask the backend to re-download a failed/lost attachment from Meta."""
        try:
            result = await self.client.execute(RETRY_MEDIA_MUTATION, {"messageId": message_id})
            payload = (result or {}).get("retryMediaDownload") or {}
            msg = payload.get("message")
            return {
                "success": bool(payload.get("success")),
                "error": payload.get("error"),
                "message": ChatMessage.from_dict(msg) if msg else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error retrying media download for %s: %s", message_id, exc)
            return {"success": False, "error": str(exc), "message": None}
