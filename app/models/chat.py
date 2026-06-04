"""DTOs for the WhatsApp chat feature."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..utils.datetime_helpers import parse_iso_datetime


@dataclass
class ChatContact:
    id: int
    wa_id: str
    phone_number: str
    name: Optional[str] = None
    profile_name: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or self.profile_name or self.phone_number or self.wa_id

    @classmethod
    def from_dict(cls, d: dict) -> "ChatContact":
        d = d or {}
        return cls(
            id=int(d.get("id") or 0),
            wa_id=d.get("waId") or "",
            phone_number=d.get("phoneNumber") or "",
            name=d.get("name"),
            profile_name=d.get("profileName"),
        )


@dataclass
class ChatMessage:
    id: int
    conversation_id: int
    contact_id: int
    direction: str
    message_type: str
    text_content: Optional[str] = None
    timestamp: Optional[datetime] = None
    wa_message_id: Optional[str] = None
    media_url: Optional[str] = None

    @property
    def is_inbound(self) -> bool:
        return self.direction == "inbound"

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        d = d or {}
        return cls(
            id=int(d.get("id") or 0),
            conversation_id=int(d.get("conversationId") or 0),
            contact_id=int(d.get("contactId") or 0),
            direction=d.get("direction") or "inbound",
            message_type=d.get("messageType") or "text",
            text_content=d.get("textContent"),
            timestamp=parse_iso_datetime(d.get("timestamp")),
            wa_message_id=d.get("waMessageId"),
            media_url=d.get("mediaUrl"),
        )


@dataclass
class ChatConversation:
    id: int
    status: str
    contact: ChatContact
    last_message: Optional[ChatMessage] = None
    last_activity: Optional[datetime] = None
    unread_count: int = 0

    @property
    def display_name(self) -> str:
        return self.contact.display_name

    @classmethod
    def from_dict(cls, d: dict) -> "ChatConversation":
        d = d or {}
        last_message = d.get("lastMessage")
        return cls(
            id=int(d.get("id") or 0),
            status=d.get("status") or "active",
            contact=ChatContact.from_dict(d.get("contact") or {}),
            last_message=ChatMessage.from_dict(last_message) if last_message else None,
            last_activity=parse_iso_datetime(d.get("lastActivity")),
            unread_count=int(d.get("unreadCount") or 0),
        )
