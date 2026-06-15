"""DTOs for the WhatsApp chat feature."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.config import Config
from ..utils.datetime_helpers import parse_iso_datetime


def _chat_local_timezone():
    try:
        return ZoneInfo(Config.TIMEZONE)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo


def _parse_chat_timestamp(value: Optional[str]) -> Optional[datetime]:
    timestamp = parse_iso_datetime(value)
    if timestamp is None:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(_chat_local_timezone())


@dataclass
class ChatContact:
    id: int
    wa_id: str
    phone_number: str
    name: Optional[str] = None
    profile_name: Optional[str] = None
    member_id: Optional[int] = None
    member_name: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.member_name or self.name or self.profile_name or self.phone_number or self.wa_id

    @property
    def secondary_identity(self) -> str:
        primary = (self.display_name or "").strip()
        number = (self.phone_number or self.wa_id or "").strip()
        whatsapp_name = (self.name or self.profile_name or "").strip()

        if whatsapp_name and whatsapp_name != primary:
            if number and number != whatsapp_name:
                return f"{whatsapp_name} - {number}"
            return whatsapp_name

        if number and number != primary:
            return number

        return ""

    @classmethod
    def from_dict(cls, d: dict) -> "ChatContact":
        d = d or {}
        raw_member_id = d.get("memberId")
        return cls(
            id=int(d.get("id") or 0),
            wa_id=d.get("waId") or "",
            phone_number=d.get("phoneNumber") or "",
            name=d.get("name"),
            profile_name=d.get("profileName"),
            member_id=int(raw_member_id) if raw_member_id is not None else None,
            member_name=d.get("memberName"),
        )


# Message types whose payload is a downloadable attachment.
MEDIA_MESSAGE_TYPES = {"image", "audio", "video", "document", "sticker"}


@dataclass
class ChatMedia:
    """Attachment metadata of a chat message."""

    id: int
    media_type: str
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    caption: Optional[str] = None
    file_size: Optional[int] = None
    media_url: Optional[str] = None
    downloaded: bool = False
    download_failed: bool = False

    @property
    def absolute_url(self) -> Optional[str]:
        """Resolve the stored URL against the API base for relative paths."""
        if not self.media_url:
            return None
        if self.media_url.startswith(("http://", "https://")):
            return self.media_url
        return f"{Config.API_BASE_URL.rstrip('/')}/{self.media_url.lstrip('/')}"

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMedia":
        d = d or {}
        raw_size = d.get("fileSize")
        return cls(
            id=int(d.get("id") or 0),
            media_type=d.get("mediaType") or "document",
            mime_type=d.get("mimeType"),
            filename=d.get("filename"),
            caption=d.get("caption"),
            file_size=int(raw_size) if raw_size is not None else None,
            media_url=d.get("mediaUrl"),
            downloaded=bool(d.get("downloaded")),
            download_failed=bool(d.get("downloadFailed")),
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
    context_message_id: Optional[str] = None
    media_url: Optional[str] = None
    media: Optional[ChatMedia] = None

    @property
    def is_inbound(self) -> bool:
        return self.direction == "inbound"

    @property
    def is_media(self) -> bool:
        return self.message_type in MEDIA_MESSAGE_TYPES

    @property
    def is_reaction(self) -> bool:
        return self.message_type == "reaction"

    @property
    def reaction_emoji(self) -> str:
        """The reaction emoji; empty string means the reaction was removed."""
        return (self.text_content or "").strip()

    @property
    def reaction_target_wa_id(self) -> Optional[str]:
        """wa_message_id of the message this reaction targets."""
        return self.context_message_id

    @property
    def media_pending(self) -> bool:
        """The backend has not finished downloading the attachment yet."""
        if not self.is_media:
            return False
        if self.media is None:
            return True
        return not self.media.downloaded and not self.media.download_failed

    @property
    def media_failed(self) -> bool:
        return self.is_media and self.media is not None and self.media.download_failed

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        d = d or {}
        raw_media = d.get("media")
        return cls(
            id=int(d.get("id") or 0),
            conversation_id=int(d.get("conversationId") or 0),
            contact_id=int(d.get("contactId") or 0),
            direction=d.get("direction") or "inbound",
            message_type=d.get("messageType") or "text",
            text_content=d.get("textContent"),
            timestamp=_parse_chat_timestamp(d.get("timestamp")),
            wa_message_id=d.get("waMessageId"),
            context_message_id=d.get("contextMessageId"),
            media_url=d.get("mediaUrl"),
            media=ChatMedia.from_dict(raw_media) if raw_media else None,
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
            last_activity=_parse_chat_timestamp(d.get("lastActivity")),
            unread_count=int(d.get("unreadCount") or 0),
        )
