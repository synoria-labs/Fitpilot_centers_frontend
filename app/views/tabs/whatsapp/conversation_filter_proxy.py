"""Client-side filter for the conversation list, by linked member's membership.

The membership status is not a backend query parameter; it already travels with each
conversation (``contact.member_membership``). So we filter on the client with a
``QSortFilterProxyModel`` wrapping ``ConversationListModel``: the source model keeps all
its incremental-update bookkeeping (upsert / apply_message / move-to-top) and the proxy
re-evaluates membership on every change thanks to ``setDynamicSortFilter``.
"""
from typing import Optional, Set

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel

from .conversation_list_model import CONVERSATION_ROLE
from .membership_chip import membership_status_category

# Membership filter key -> accepted categories. ``None`` means accept everything.
_FILTER_CATEGORIES: dict[str, Optional[Set[str]]] = {
    "all": None,
    "active": {"active"},
    "expired": {"expired"},
    "none": {"none"},
}
# "unread" is not a membership category; it filters on conv.unread_count (handled separately).
_VALID_KEYS = set(_FILTER_CATEGORIES) | {"unread"}


class ConversationFilterProxy(QSortFilterProxyModel):
    """Filters conversations by membership category or unread state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_key = "all"
        self._pinned_id: Optional[int] = None
        # Re-run filterAcceptsRow when the source model mutates (realtime/upsert).
        self.setDynamicSortFilter(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_filter_key(self, key: str) -> None:
        key = key if key in _VALID_KEYS else "all"
        if key == self._filter_key:
            return
        self._filter_key = key
        self._pinned_id = None  # a fresh filter starts unpinned
        self.invalidateFilter()

    def filter_key(self) -> str:
        return self._filter_key

    def set_pinned_conversation(self, conversation_id: Optional[int]) -> None:
        """Keep one conversation visible regardless of the filter.

        Used so the chat the user just opened doesn't vanish from the "No leídos" filter
        the instant it's marked read (its unread count hits 0). Cleared on filter change.
        """
        if conversation_id == self._pinned_id:
            return
        self._pinned_id = conversation_id
        self.invalidateFilter()

    # ------------------------------------------------------------------
    # QSortFilterProxyModel
    # ------------------------------------------------------------------
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if self._filter_key == "all":
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        conv = index.data(CONVERSATION_ROLE)
        if conv is None:
            return False
        if self._pinned_id is not None and conv.id == self._pinned_id:
            return True
        if self._filter_key == "unread":
            return (conv.unread_count or 0) > 0
        accepted = _FILTER_CATEGORIES.get(self._filter_key)
        if accepted is None:
            return True
        return membership_status_category(conv.contact.member_membership) in accepted
