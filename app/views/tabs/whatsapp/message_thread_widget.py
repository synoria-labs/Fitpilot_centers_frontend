"""Scrollable list of message bubbles for a conversation, laid out like WhatsApp: a day
chip where the day changes, the tail only on the first bubble of each sender's run and
replies quoting the message they answer."""
from datetime import date, datetime
from typing import Dict, List, Optional, Set

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ....models.chat import ChatMessage
from . import theme
from .message_bubble import MessageBubble, QuotedMessage
from .message_formatter import day_label, quote_text_for_message
from .theme import WaPalette
from .wa_mockup import ScrollDownButton, day_chip_qss


_BOTTOM_THRESHOLD_PX = 48
_SCROLL_RETRY_COUNT = 4
_SCROLL_RETRY_MS = 16
_SCROLL_ANIMATION_MS = 180
_OWN_AUTHOR = "Tú"  # how WhatsApp names the business's own messages in a quote


class DayChip(QWidget):
    """Centered day separator («Hoy», «Ayer»…), the same chip as the template preview's."""

    def __init__(self, text: str, pal: WaPalette, parent=None) -> None:
        super().__init__(parent)
        self.text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 4)
        label = QLabel(text)
        label.setStyleSheet(day_chip_qss(pal))
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)


class MessageThreadWidget(QScrollArea):
    retry_requested = Signal(int)  # message id (re-emitted from bubbles)
    reaction_requested = Signal(str, str)  # target wa_message_id, emoji ("" removes)

    def __init__(self, parent=None, *, pal: Optional[WaPalette] = None) -> None:
        super().__init__(parent)
        self._pal = pal or theme.app_palette()
        self.setWidgetResizable(True)
        self.setObjectName("threadScroll")

        self._container = QWidget()
        self._container.setObjectName("threadContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 12)
        self._layout.setSpacing(0)
        self._layout.addStretch()  # index 0: keeps bubbles stacked from the top

        self.setWidget(self._container)
        # Show the conversation pane's painted background through the scroll area:
        # transparent frame + container, and a non-autofilled viewport.
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet(
            "#threadScroll { border: none; background: transparent; }"
            " #threadContainer { background: transparent; }"
        )

        self._contact_name = ""
        self._seen_ids: Set[int] = set()
        self._bubbles: Dict[int, MessageBubble] = {}
        self._bubbles_by_wa: Dict[str, MessageBubble] = {}  # wa_message_id -> bubble
        self._messages_by_wa: Dict[str, ChatMessage] = {}  # wa_message_id -> message (quotes)
        self._reactions_by_wa: Dict[str, dict] = {}  # target wa_id -> {"inbound": e, "outbound": e}
        self._last_day: Optional[date] = None
        self._last_direction: Optional[str] = None
        self._pending_scroll_mode = ""
        self._pending_scroll_attempts = 0

        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(_SCROLL_ANIMATION_MS)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._jump_button = ScrollDownButton(
            self._pal, self.viewport(), tooltip="Ir al mensaje más reciente"
        )
        self._jump_button.clicked.connect(self._on_jump_to_latest_clicked)

        self.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

    def set_contact_name(self, name: str) -> None:
        """Author shown when a reply quotes one of the contact's messages."""
        self._contact_name = name or ""

    def set_messages(self, messages: List[ChatMessage]) -> None:
        self._clear()
        self.clear_new_message_indicator()
        for m in messages:
            if m.is_reaction:
                self._apply_reaction(m)
            else:
                self._add(m)
        self.scroll_to_bottom(animated=False)

    def append_message(
        self,
        message: ChatMessage,
        *,
        force_scroll: bool = False,
        show_new_message_button: bool = True,
    ) -> None:
        if message.is_reaction:
            # Reactions attach to an existing bubble; never a standalone bubble,
            # no scroll, no "new message" indicator.
            self._apply_reaction(message)
            return
        if message.id and message.id in self._seen_ids:
            return
        was_near_bottom = self.is_near_bottom()
        self._add(message)

        if force_scroll or was_near_bottom:
            self.clear_new_message_indicator()
            self.scroll_to_bottom(animated=True)
        elif show_new_message_button:
            self._show_new_message_indicator()

    def clear_new_message_indicator(self) -> None:
        self._jump_button.hide()

    def is_near_bottom(self) -> bool:
        scrollbar = self.verticalScrollBar()
        return scrollbar.maximum() - scrollbar.value() <= _BOTTOM_THRESHOLD_PX

    def scroll_to_bottom(self, *, animated: bool) -> None:
        self._pending_scroll_mode = "smooth" if animated else "instant"
        self._pending_scroll_attempts = _SCROLL_RETRY_COUNT
        self._apply_pending_scroll()

    def update_message(self, message: ChatMessage) -> None:
        """Replace the bubble of an existing message in place (e.g. when its
        media download finished). Preserves the scroll position; re-anchors to
        the bottom when the user was already there."""
        old_bubble = self._bubbles.get(message.id)
        if old_bubble is None:
            return
        index = self._layout.indexOf(old_bubble)
        if index < 0:
            return

        was_near_bottom = self.is_near_bottom()
        self._layout.takeAt(index)
        old_bubble.deleteLater()

        if message.wa_message_id:
            self._messages_by_wa[message.wa_message_id] = message
        bubble = self._make_bubble(message, tail=old_bubble.has_tail)
        self._layout.insertWidget(index, bubble)
        self._bubbles[message.id] = bubble

        if was_near_bottom:
            self.scroll_to_bottom(animated=False)

    def _make_bubble(self, message: ChatMessage, *, tail: bool) -> MessageBubble:
        bubble = MessageBubble(message, pal=self._pal, tail=tail, quote=self._quote_for(message))
        bubble.retry_requested.connect(self.retry_requested.emit)
        bubble.reaction_requested.connect(self._on_reaction_requested)
        if message.wa_message_id:
            self._bubbles_by_wa[message.wa_message_id] = bubble
            known = self._reactions_by_wa.get(message.wa_message_id)
            if known:
                bubble.set_reactions(known)
        return bubble

    def _quote_for(self, message: ChatMessage) -> Optional[QuotedMessage]:
        """The quote box of a reply, when the message it answers is in this thread."""
        quoted = self._messages_by_wa.get(message.context_message_id or "")
        if quoted is None:
            return None
        if quoted.is_inbound:
            author = self._contact_name or "Contacto"
            return QuotedMessage(author, quote_text_for_message(quoted), theme.avatar_color(author))
        return QuotedMessage(_OWN_AUTHOR, quote_text_for_message(quoted), self._pal.quote_name)

    def _on_reaction_requested(self, target_wa_id: str, emoji: str) -> None:
        self.reaction_requested.emit(target_wa_id, emoji)

    def _apply_reaction(self, message: ChatMessage) -> None:
        """Attach (or clear) a reaction emoji on its target bubble.

        Reactions are kept per reactor direction so a contact's and our own
        reaction can both show. Latest event wins per direction; an empty emoji
        removes that side's reaction. If the target bubble is not loaded yet, the
        state is stashed and applied when the bubble appears (see ``_make_bubble``).
        """
        target = message.reaction_target_wa_id
        if not target:
            return
        slot = self._reactions_by_wa.setdefault(target, {})
        if message.reaction_emoji:
            slot[message.direction] = message.reaction_emoji
        else:
            slot.pop(message.direction, None)
        bubble = self._bubbles_by_wa.get(target)
        if bubble is not None:
            bubble.set_reactions(slot)

    def _add(self, message: ChatMessage) -> None:
        if message.id:
            if message.id in self._seen_ids:
                return
            self._seen_ids.add(message.id)
        if message.timestamp is not None:
            day = message.timestamp.date()
            if day != self._last_day:
                today = datetime.now(message.timestamp.tzinfo).date()
                self._layout.addWidget(DayChip(day_label(day, today), self._pal))
                self._last_day = day
                self._last_direction = None  # a new day starts a new run
        if message.wa_message_id:
            self._messages_by_wa[message.wa_message_id] = message
        bubble = self._make_bubble(message, tail=message.direction != self._last_direction)
        self._last_direction = message.direction
        self._layout.addWidget(bubble)
        if message.id:
            self._bubbles[message.id] = bubble

    def _clear(self) -> None:
        self._seen_ids.clear()
        self._bubbles.clear()
        self._bubbles_by_wa.clear()
        self._messages_by_wa.clear()
        self._reactions_by_wa.clear()
        self._last_day = None
        self._last_direction = None
        while self._layout.count() > 1:  # keep the leading stretch at index 0
            item = self._layout.takeAt(self._layout.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_new_message_indicator(self) -> None:
        self._position_jump_button()
        self._jump_button.show()
        self._jump_button.raise_()

    def _on_jump_to_latest_clicked(self) -> None:
        self.clear_new_message_indicator()
        self.scroll_to_bottom(animated=True)

    def _on_scroll_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._pending_scroll_mode == "instant":
            self.verticalScrollBar().setValue(maximum)
        elif self._pending_scroll_mode == "smooth":
            self._scroll_animation.setEndValue(maximum)
        self._position_jump_button()

    def _on_scroll_value_changed(self, _value: int) -> None:
        if self.is_near_bottom():
            self.clear_new_message_indicator()

    def _apply_pending_scroll(self) -> None:
        if not self._pending_scroll_mode:
            return

        scrollbar = self.verticalScrollBar()
        target = scrollbar.maximum()
        if self._pending_scroll_mode == "instant":
            self._scroll_animation.stop()
            scrollbar.setValue(target)

        self._pending_scroll_attempts -= 1
        if self._pending_scroll_attempts > 0:
            QTimer.singleShot(_SCROLL_RETRY_MS, self._apply_pending_scroll)
            return

        mode = self._pending_scroll_mode
        self._pending_scroll_mode = ""

        if mode == "smooth":
            self._animate_to_bottom()
        else:
            scrollbar.setValue(scrollbar.maximum())

    def _animate_to_bottom(self) -> None:
        scrollbar = self.verticalScrollBar()
        target = scrollbar.maximum()
        if scrollbar.value() == target:
            return
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(scrollbar.value())
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.start()

    def _position_jump_button(self) -> None:
        x = self.viewport().width() - self._jump_button.width() - 14
        y = self.viewport().height() - self._jump_button.height() - 10
        self._jump_button.move(max(0, x), max(0, y))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_jump_button()
