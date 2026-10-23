"""Paneles de resultados de una campaña: tarjetas, embudo y destinatarios.

El panel de resultados era un único ``QLabel`` con toda la información concatenada; aquí se
separa en tarjetas comparables (mismo lenguaje visual que Dashboard y Finanzas) más un
desglose por destinatario. Ese desglose es la parte que faltaba: la API
``campaignRecipients`` estaba implementada de punta a punta y ninguna vista la llamaba, así
que cuando una campaña fallaba no había forma de ver *a quién* ni *por qué*.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QGroupBox, QCheckBox, QPushButton, QSpinBox,
)

from ...table_widget_helpers import configure_table_widget
from ...widgets.compact_metric_card import CompactMetricCard
from ....utils.datetime_helpers import format_local_datetime

# Accents mirror Finanzas/Dashboard so a number means the same thing across screens.
_ACCENT_SENT = "#3498db"
_ACCENT_DELIVERED = "#1abc9c"
_ACCENT_READ = "#9b59b6"
_ACCENT_CONVERTED = "#2ecc71"
_ACCENT_REVENUE = "#f1c40f"

_RECIPIENT_STATUS_LABELS = {
    "pending": "Pendiente",
    "sending": "Enviando",
    "sent": "Enviado",
    "delivered": "Entregado",
    "read": "Leído",
    "replied": "Respondió",
    "failed": "Falló",
    "skipped": "Omitido",
    "opted_out": "Sin consentimiento",
    "needs_review": "Requiere revisión",
}

# Why a member was left out. Shown verbatim in the table so "omitido" is never a dead end.
_SKIP_REASON_LABELS = {
    "no_phone": "sin número de WhatsApp",
    "no_consent": "revocó el consentimiento",
    "recency_block": "contactado hace poco",
    "daily_cap": "ya recibió marketing hoy",
    "quiet_hours": "esperando fuera de horario",
    "pending_action": "conversación en curso",
    "rate_limited": "reintento por límite de envío",
    "meta_rejected": "rechazado por Meta",
    "meta_retry": "reintento programado por límite de Meta",
    "duplicate_phone": "número repetido en esta campaña",
    "already_delivered": "este número ya recibió la campaña",
    "awaiting_delivery": "esperando confirmación de Meta",
    "uncertain_previous_send": "intento anterior pendiente de revisión",
    "event_closed": "el evento ya no está a la venta",
    "phone_identity_mismatch": "revisar la identidad del número de WhatsApp",
    "legacy_link_mismatch": "revisar el vínculo con el mensaje histórico",
    "uncertain_send": "no se ha podido confirmar el resultado del envío",
}


def recipient_status_label(status: Optional[str]) -> str:
    return _RECIPIENT_STATUS_LABELS.get(status or "", status or "")


def skip_reason_label(reason: Optional[str]) -> str:
    if not reason:
        return ""
    return _SKIP_REASON_LABELS.get(reason, reason)


class MetricsPanel(QWidget):
    """Tarjetas + embudo de una campaña."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        cards = QGridLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setHorizontalSpacing(8)
        cards.setVerticalSpacing(8)
        self.card_sent = CompactMetricCard("Enviados", "📤", _ACCENT_SENT)
        self.card_accepted = CompactMetricCard("Aceptados por Meta", "📨", _ACCENT_SENT)
        self.card_delivered = CompactMetricCard("Entregados", "✅", _ACCENT_DELIVERED)
        self.card_read = CompactMetricCard("Leídos", "👁", _ACCENT_READ)
        self.card_converted = CompactMetricCard("Conversiones", "🎯", _ACCENT_CONVERTED)
        self.card_revenue = CompactMetricCard("Ingreso recuperado", "💰", _ACCENT_REVENUE)
        for column, card in enumerate(
            (
                self.card_accepted,
                self.card_sent,
                self.card_delivered,
                self.card_read,
                self.card_converted,
                self.card_revenue,
            )
        ):
            cards.addWidget(card, column // 3, column % 3)
        layout.addLayout(cards)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v de %m enviados")
        self.progress.setVisible(False)
        progress_row.addWidget(self.progress, 1)
        layout.addLayout(progress_row)

        self.detail_label = QLabel("Selecciona o guarda una campaña para ver métricas.")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

    def clear(self, message: str = "Guarda la campaña para enviar y ver métricas.") -> None:
        for card in (
            self.card_accepted,
            self.card_sent,
            self.card_delivered,
            self.card_read,
            self.card_converted,
            self.card_revenue,
        ):
            card.set_value("—")
        self.progress.setVisible(False)
        self.detail_label.setText(message)

    def set_metrics(self, metrics: Dict[str, Any], *, sending: bool = False) -> None:
        metrics = metrics or {}
        self.card_accepted.set_value(str(metrics.get("accepted", 0)), "solicitudes aceptadas")
        sent = int(metrics.get("sent", 0) or 0)
        targeted = int(metrics.get("targeted", 0) or 0)
        pending = int(metrics.get("pending", 0) or 0)

        def pct(key: str) -> str:
            return f"{round(float(metrics.get(key, 0) or 0) * 100, 1)}%"

        self.card_sent.set_value(str(sent), f"de {targeted} en la audiencia")
        self.card_delivered.set_value(
            str(metrics.get("delivered", 0)), f"{pct('delivery_rate')} de los enviados"
        )
        self.card_read.set_value(
            str(metrics.get("read", 0)), f"{pct('read_rate')} de los enviados"
        )
        self.card_converted.set_value(
            str(metrics.get("converted", 0)), f"{pct('conversion_rate')} de los enviados"
        )
        self.card_revenue.set_value(
            f"${float(metrics.get('revenue_recovered', 0) or 0):,.2f}",
            f"{metrics.get('replied', 0)} respuesta(s)",
        )

        # Only meaningful while a run is in flight; a finished campaign shows the cards alone.
        self.progress.setVisible(bool(sending) and targeted > 0)
        if self.progress.isVisible():
            self.progress.setMaximum(max(targeted, 1))
            self.progress.setValue(min(sent, targeted))

        parts = [
            f"Teléfonos únicos: {metrics.get('unique_phones', 0)}",
            f"Duplicados: {metrics.get('duplicates', 0)}",
            f"Rechazados por Meta: {metrics.get('rejected', 0)}",
            f"Reintentos programados: {metrics.get('retry_pending', 0)}",
            f"En revisión: {metrics.get('needs_review', 0)}",
            f"Pendientes: {pending}",
            f"Fallidos: {metrics.get('failed', 0)}",
            f"Omitidos: {metrics.get('skipped', 0)}",
            f"Sin consentimiento: {metrics.get('opted_out', 0)}",
        ]
        errors = ", ".join(f"{code}: {count}" for code, count in (metrics.get("error_counts") or {}).items())
        source = (f"Webhooks de Meta · Plantilla #{metrics.get('template_id') or '—'} · "
                  f"Periodo: {format_local_datetime(metrics.get('period_start'))} a {format_local_datetime(metrics.get('period_end'))} · "
                  f"Actualizado: {format_local_datetime(metrics.get('updated_at'))} (hora de México). "
                  "La aceptación no acredita entrega. El panel agregado de Meta puede actualizarse después.")
        self.detail_label.setText(" · ".join(parts) + (f"\nErrores Meta: {errors}" if errors else "") + "\n" + source)


class RecipientsTable(QWidget):
    """Quién recibió la campaña, en qué estado quedó y por qué."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("Ver:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos", None)
        for key, label in _RECIPIENT_STATUS_LABELS.items():
            self.status_filter.addItem(label, key)
        filter_row.addWidget(self.status_filter)
        filter_row.addStretch()
        self.summary_label = QLabel("")
        filter_row.addWidget(self.summary_label)
        layout.addLayout(filter_row)

        self._class_names: Dict[int, str] = {}

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("campRecipientsTable")
        self.table.setHorizontalHeaderLabels(["Teléfono", "Estado", "Motivo / error", "Clase", "Intentos", "Próximo envío"])
        configure_table_widget(self.table)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

    def set_class_names(self, names: Dict[int, str]) -> None:
        """Ids -> nombres de clase, para mostrar la afinidad en lugar de un número."""
        self._class_names = dict(names or {})

    def set_recipients(self, recipients: List[Dict[str, Any]]) -> None:
        recipients = recipients or []
        class_names = self._class_names
        self.table.setRowCount(0)
        for recipient in recipients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(recipient.get("phone_e164") or "—"))
            self.table.setItem(
                row, 1, QTableWidgetItem(recipient_status_label(recipient.get("status")))
            )
            # The error wins over the skip reason: if something went wrong, that is the
            # thing the operator needs to read.
            detail = recipient.get("error") or skip_reason_label(recipient.get("skip_reason"))
            self.table.setItem(row, 2, QTableWidgetItem(detail or ""))
            attempts = recipient.get("attempts") or []
            item = QTableWidgetItem(str(sum(a.get("state") != "not_sent" for a in attempts)))
            item.setToolTip("\n".join(f"{format_local_datetime(a.get('started_at'))}: {a.get('state')} · "
                                      f"{a.get('error_code') or ''} {a.get('error_detail') or ''} · "
                                      f"{a.get('wa_message_id') or ''}" for a in attempts))
            self.table.setItem(row, 4, item)
            self.table.setItem(row, 5, QTableWidgetItem(format_local_datetime(recipient.get("send_after"))))
            class_id = recipient.get("favorite_class_type_id")
            self.table.setItem(
                row, 3, QTableWidgetItem(class_names.get(class_id, "") if class_id else "")
            )
        self.summary_label.setText(f"{len(recipients)} destinatario(s)")

    def selected_status(self) -> Optional[str]:
        return self.status_filter.currentData()


class DeliveryPolicyPanel(QGroupBox):
    """Saving policy and scheduling recovery are separate administrator actions."""
    def __init__(self, parent=None):
        super().__init__("Frecuencia y recuperación", parent)
        layout = QVBoxLayout(self)
        self.policy = QComboBox()
        self.policy.addItem("Respetar límite diario y omitir", "respect")
        self.policy.addItem("Reprogramar al próximo día permitido", "defer")
        self.policy.addItem("Exceptuar esta campaña del límite diario de FitPilot", "allow_additional")
        layout.addWidget(self.policy)
        self.retry_meta = QCheckBox("Reintentar límites de Meta (131049): después de 24 h y una última vez 48 h después")
        self.retry_meta.setChecked(True)
        layout.addWidget(self.retry_meta)
        row = QHBoxLayout()
        row.addWidget(QLabel("Bloqueo entre campañas por contacto reciente (días):"))
        self.recency = QSpinBox()
        self.recency.setRange(0, 3650)
        self.recency.setValue(30)
        row.addWidget(self.recency)
        row.addStretch()
        layout.addLayout(row)
        hint = QLabel("La excepción no evita restricciones de Meta ni vuelve a enviar esta campaña a números que ya la recibieron. "
                      "Guardar la política no inicia una recuperación.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("Guardar política")
        self.recover_button = QPushButton("Recuperar no entregados…")
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.recover_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def values(self):
        return {"dailyCapPolicy": self.policy.currentData(), "autoRetryMetaLimits": self.retry_meta.isChecked()}

    def load(self, campaign):
        self.policy.setCurrentIndex(max(0, self.policy.findData(campaign.get("daily_cap_policy", "respect"))))
        self.retry_meta.setChecked(campaign.get("auto_retry_meta_limits", False))
        self.recency.setValue(campaign.get("recency_block_days") or 0)
