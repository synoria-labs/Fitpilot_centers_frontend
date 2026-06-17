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

# Filter key -> accepted membership categories. ``None`` means accept everything.
_FILTER_CATEGORIES: dict[str, Optional[Set[str]]] = {
    "all": None,
    "active": {"active"},
    "expired": {"expired"},
    "none": {"none"},
}


class ConversationFilterProxy(QSortFilterProxyModel):
    """Filters conversations by the linked member's membership category."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_key = "all"
        # Re-run filterAcceptsRow when the source model mutates (realtime/upsert).
        self.setDynamicSortFilter(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_filter_key(self, key: str) -> None:
        key = key if key in _FILTER_CATEGORIES else "all"
        if key == self._filter_key:
            return
        self._filter_key = key
        self.invalidateFilter()

    def filter_key(self) -> str:
        return self._filter_key

    # ------------------------------------------------------------------
    # QSortFilterProxyModel
    # ------------------------------------------------------------------
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        accepted = _FILTER_CATEGORIES.get(self._filter_key)
        if accepted is None:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        conv = index.data(CONVERSATION_ROLE)
        if conv is None:
            return False
        return membership_status_category(conv.contact.member_membership) in accepted
