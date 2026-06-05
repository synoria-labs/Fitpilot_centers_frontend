"""List model backing the conversation list (chats).

Holds the conversations as plain data and exposes each ``ChatConversation`` via a
custom role so a ``QStyledItemDelegate`` can paint rows without per-row widgets.
Supports incremental updates (upsert / promote-to-top / apply realtime message) so
the view never has to rebuild the whole list on every message.
"""
from typing import Dict, List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ....models.chat import ChatConversation, ChatMessage

# Role that yields the full ChatConversation object for the delegate.
CONVERSATION_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class ConversationListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: List[ChatConversation] = []
        self._index_by_id: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Qt model interface
    # ------------------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        conv = self._items[index.row()]
        if role == CONVERSATION_ROLE:
            return conv
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return conv.display_name
        return None

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def conversation_at(self, row: int) -> Optional[ChatConversation]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def get(self, conversation_id: int) -> Optional[ChatConversation]:
        row = self._index_by_id.get(conversation_id)
        return self._items[row] if row is not None else None

    def index_of(self, conversation_id: int) -> Optional[int]:
        return self._index_by_id.get(conversation_id)

    def _reindex(self) -> None:
        self._index_by_id = {conv.id: i for i, conv in enumerate(self._items)}

    # ------------------------------------------------------------------
    # Bulk updates (first page / pagination)
    # ------------------------------------------------------------------
    def reset(self, conversations: List[ChatConversation]) -> None:
        self.beginResetModel()
        self._items = list(conversations or [])
        self._reindex()
        self.endResetModel()

    def append(self, conversations: List[ChatConversation]) -> None:
        new_items = [c for c in (conversations or []) if c.id not in self._index_by_id]
        if not new_items:
            return
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(new_items) - 1)
        self._items.extend(new_items)
        self._reindex()
        self.endInsertRows()

    # ------------------------------------------------------------------
    # Incremental updates (send / realtime)
    # ------------------------------------------------------------------
    def upsert(self, conversation: ChatConversation, promote: bool = True) -> None:
        """Insert a new conversation at the top, or update an existing one in place."""
        existing_row = self._index_by_id.get(conversation.id)
        if existing_row is None:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._items.insert(0, conversation)
            self._reindex()
            self.endInsertRows()
            return

        self._items[existing_row] = conversation
        if promote and existing_row != 0:
            self._move_to_top(existing_row)
        else:
            idx = self.index(existing_row)
            self.dataChanged.emit(idx, idx)

    def apply_message(self, message: ChatMessage) -> bool:
        """Update an already-loaded conversation from a new message and promote it.

        Returns False when the conversation is not loaded (caller should fetch it).
        """
        row = self._index_by_id.get(message.conversation_id)
        if row is None:
            return False
        conv = self._items[row]
        conv.last_message = message
        if message.timestamp is not None:
            conv.last_activity = message.timestamp
        if row != 0:
            self._move_to_top(row)
        else:
            idx = self.index(0)
            self.dataChanged.emit(idx, idx)
        return True

    def _move_to_top(self, row: int) -> None:
        # destination 0 is valid here because row >= 1.
        self.beginMoveRows(QModelIndex(), row, row, QModelIndex(), 0)
        conv = self._items.pop(row)
        self._items.insert(0, conv)
        self._reindex()
        self.endMoveRows()
        idx = self.index(0)
        self.dataChanged.emit(idx, idx)
