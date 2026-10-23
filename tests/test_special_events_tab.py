"""Pantalla «Eventos especiales»: mapeo del servicio, controller y humo con Qt offscreen.

Lo importante que se comprueba: que las horas viajen como hora local de la sede (nunca la de
la PC ni UTC), que la sustitución sólo se pueda aplicar después de una vista previa y de
marcar el «entiendo», y que la pantalla muestre lo que el servidor decidió.
"""
from __future__ import annotations

import pytest

from app.services.special_events_service import SpecialEventsService, map_detail
from app.utils.datetime_helpers import format_local_datetime

EVENT_NODE = {
    "id": "7",
    "name": "Halloween · 2.º aniversario",
    "description": "Noche de spinning",
    "includes": "Kit\nSnacks",
    "address": "Las Rosas #101",
    "venueId": 1,
    "venueName": "Love fitness Bugambilias",
    "venueAddress": "Rinconada Bugambilias",
    "classTypeId": 3,
    "instructorId": 343,
    "instructorName": "Laura Torres Camarillo",
    "timezone": "America/Mexico_City",
    "startAt": "2026-10-31T01:00:00+00:00",
    "endAt": None,
    "localDate": "2026-10-30",
    "localStartTime": "19:00",
    "localEndTime": None,
    "scheduleLabel": "viernes 30 de octubre de 2026, a las 19:00",
    "price": 500.0,
    "currency": "MXN",
    "capacity": None,
    "holdMinutes": 30,
    "status": "draft",
    "sold": 0,
    "held": 0,
    "available": None,
    "salesOpen": False,
    "salesClosedReason": "El evento todavía no está publicado.",
    "publishBlockers": ["Falta la hora de fin (la duración) del evento.", "Falta el cupo del evento."],
    "paymentsReady": True,
    "paymentsWarning": None,
    "activeTakeovers": 0,
    "pendingFollowUps": 1,
    "cancelReason": None,
    "publishedAt": None,
    "canceledAt": None,
    "createdAt": "2026-10-21T22:00:00+00:00",
    "seats": [
        {"seatId": 11, "label": "Bicicleta 1", "status": "sold"},
        {"seatId": 12, "label": "Bicicleta 2", "status": "held"},
        {"seatId": 13, "label": "Bicicleta 3", "status": "free"},
    ],
    "linkedCampaigns": [{"id": 4, "name": "Halloween 2026", "status": "draft"}],
}

DETAIL_NODE = {
    "event": EVENT_NODE,
    "orders": [
        {
            "id": 1, "participantName": "Ana López", "participantPhone": "8711234567", "personId": None,
            "seatId": 11, "seatLabel": "Bicicleta 1", "status": "paid", "channel": "whatsapp",
            "amount": 500.0, "currency": "MXN", "paymentMethod": "mercadopago",
            "paidAt": "2026-10-22T01:30:00+00:00", "holdExpiresAt": None, "mpStatus": "approved",
            "mpPaymentId": "123", "reviewReason": None, "cancelReason": None, "refundedAt": None,
            "notes": None, "createdAt": "2026-10-22T01:00:00+00:00",
        },
        {
            "id": 2, "participantName": "Beto", "participantPhone": "8719876543", "personId": None,
            "seatId": 12, "seatLabel": "Bicicleta 2", "status": "awaiting_payment", "channel": "whatsapp",
            "amount": 500.0, "currency": "MXN", "paymentMethod": None, "paidAt": None,
            "holdExpiresAt": "2026-10-22T02:30:00+00:00", "mpStatus": None, "mpPaymentId": None,
            "reviewReason": None, "cancelReason": None, "refundedAt": None, "notes": None,
            "createdAt": "2026-10-22T02:00:00+00:00",
        },
    ],
    "displacements": [
        {
            "id": 9, "eventId": 7, "eventName": "Halloween", "sessionId": 5562,
            "sessionName": "Spinning 7:00 pm", "sessionStartAt": "2026-10-31T01:00:00+00:00",
            "sessionLabel": "viernes 30 de octubre de 2026, de 19:00 a 20:00",
            "sessionStatus": "displaced", "personId": 395, "personName": "Omar Cortinas",
            "phone": "871", "seatLabel": "Bicicleta 1", "reservationId": 6423,
            "reservationStatus": "displaced", "reservationSource": "standing",
            "planName": "Plan Spinning Mensual.", "membershipEndsAt": "2026-11-02T05:59:59+00:00",
            "reason": "Clase sustituida", "followUpStatus": "pending", "notifiedAt": None,
            "notifiedByName": None, "notificationChannel": None, "notificationNotes": None,
            "compensationType": None, "compensationNotes": None, "resolvedAt": None,
            "resolvedByName": None, "restorationStatus": None, "restorationNote": None,
            "restoredAt": None,
        }
    ],
    "takeovers": [],
}


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])
        self.last_error = None

    async def execute(self, query, variables=None, use_auth=True):
        self.calls.append((query, variables))
        if not self.responses:
            self.last_error = "Error de red"
            return None
        return self.responses.pop(0)


# ---------------------------------------------------------------- servicio
def test_detail_mapping_is_snake_case_and_typed():
    detail = map_detail(DETAIL_NODE)
    event = detail["event"]
    assert event["id"] == 7 and event["local_start_time"] == "19:00"
    assert event["publish_blockers"][1] == "Falta el cupo del evento."
    assert event["seats"][2] == {"seat_id": 13, "label": "Bicicleta 3", "status": "free"}
    assert detail["orders"][1]["hold_expires_at"] == "2026-10-22T02:30:00+00:00"
    assert detail["displacements"][0]["follow_up_status"] == "pending"


@pytest.mark.asyncio
async def test_create_sends_local_wall_clock_and_only_given_fields():
    client = FakeClient([{"createSpecialEvent": {"success": True, "error": None, "message": "ok", "detail": DETAIL_NODE}}])
    service = SpecialEventsService(client)
    result = await service.create_event(
        {"name": "Halloween", "venue_id": 1, "local_date": "2026-10-30", "start_time": "19:00",
         "end_time": None, "price": 500.0, "capacity": None, "seat_ids": [11, 12]}
    )
    assert result["success"] and result["detail"]["event"]["id"] == 7
    sent = client.calls[0][1]["input"]
    assert sent == {
        "name": "Halloween", "venueId": 1, "localDate": "2026-10-30", "startTime": "19:00",
        "price": 500.0, "seatIds": [11, 12],
    }


@pytest.mark.asyncio
async def test_network_failure_surfaces_the_client_error():
    service = SpecialEventsService(FakeClient([]))
    result = await service.publish_event(7)
    assert result == {"success": False, "error": "Error de red", "message": None, "detail": None}
    with pytest.raises(RuntimeError, match="Error de red"):
        await service.list_events()


def test_server_timestamps_are_shown_in_gym_time():
    # 01:30 UTC is 19:30 the previous day in Mexico City; formatting it raw would say 01:30.
    assert format_local_datetime("2026-10-22T01:30:00+00:00") == "21/10/2026 19:30"
    assert format_local_datetime(None) == "—"


# ---------------------------------------------------------------- controller
def test_controller_routes_results_to_signals(qapp, monkeypatch):
    from app.controllers.special_events_controller import SpecialEventsController

    controller = SpecialEventsController(service=object())
    received = {"detail": [], "ok": [], "error": []}
    controller.detail_loaded.connect(received["detail"].append)
    controller.operation_succeeded.connect(received["ok"].append)
    controller.error_occurred.connect(received["error"].append)

    def fake_execute(service, method, on_success, on_error, **kwargs):
        if method == "publish_event":
            on_success({"success": False, "error": "Falta el cupo", "detail": {"event": {"id": 7}}})
        else:
            on_success({"success": True, "message": "Cambios guardados.", "detail": {"event": {"id": 7}}})

    monkeypatch.setattr(controller, "_execute_authenticated_operation", fake_execute)
    controller.update_event(7, {"name": "x"})
    controller.publish_event(7)
    assert len(received["detail"]) == 2
    assert received["ok"] == ["Cambios guardados."]
    assert received["error"] == ["Falta el cupo"]

    missing = SpecialEventsController(service=None)
    errors = []
    missing.error_occurred.connect(errors.append)
    missing.load_events()
    assert errors == ["Servicio de eventos especiales no disponible"]


# ---------------------------------------------------------------- pantalla
@pytest.fixture
def tab(qtbot, monkeypatch):
    from app.core import container
    from app.views.tabs import special_events_tab as module

    monkeypatch.setattr(module, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(module, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(module, "show_confirmation", lambda *a, **k: True)
    monkeypatch.setattr(container, "get", lambda _name: None)
    widget = module.SpecialEventsTab()
    qtbot.addWidget(widget)
    widget._apply_options({
        "default_timezone": "America/Mexico_City",
        "payments_ready": True,
        "venues": [{"id": 1, "name": "Love fitness Bugambilias", "address": "x",
                    "seats": [{"seat_id": 11, "label": "Bicicleta 1"},
                              {"seat_id": 12, "label": "Bicicleta 2"},
                              {"seat_id": 13, "label": "Bicicleta 3"}]}],
        "instructors": [{"id": 343, "name": "Laura Torres Camarillo"}],
        "class_types": [{"id": 3, "name": "Spinning"}],
    })
    return widget


def test_detail_fills_form_tables_and_explains_what_is_missing(tab):
    tab._render_detail(map_detail(DETAIL_NODE))
    assert tab.name_edit.text() == "Halloween · 2.º aniversario"
    assert tab.instructor_combo.currentData() == 343
    assert tab.start_edit.time().toString("HH:mm") == "19:00"
    assert tab.end_unknown.isChecked() and tab.capacity_unknown.isChecked()
    assert "Para publicar falta" in tab.status_label.text()
    assert not tab.publish_btn.isEnabled()  # blockers pending
    assert tab.orders_table.rowCount() == 2
    assert tab.orders_table.item(0, 3).text() == "Pagado"
    assert tab.orders_table.item(1, 6).text() == "hasta 20:30"  # local hold expiry
    assert tab.displaced_table.item(0, 5).text() == "Pendiente"
    assert "Bicis libres: Bicicleta 3" in tab.seats_summary.text()
    assert "«Halloween 2026»" in tab.linked_label.text()


def test_takeover_needs_preview_and_explicit_confirmation(tab, monkeypatch):
    tab._render_detail(map_detail(DETAIL_NODE))
    applied = []
    monkeypatch.setattr(tab.controller, "apply_takeover", lambda eid, ids: applied.append((eid, ids)))
    assert not tab.apply_takeover_btn.isEnabled()

    tab._render_takeover_preview({
        "event_id": 7, "pending_session_ids": [5562], "affected_clients": 3, "blockers": [],
        "summary": "Se sustituirá 1 clase(s)",
        "sessions": [{"session_id": 5562, "name": "Spinning 7:00 pm", "label": "viernes",
                      "taken_by_this_event": False, "clients": [
                          {"person_name": "Omar", "phone": "871", "seat_label": "Bicicleta 1",
                           "plan_name": "Mensual", "membership_ends_at": None, "source": "standing",
                           "without_reservation": False}]}],
    })
    assert tab.preview_table.rowCount() == 1
    assert not tab.apply_takeover_btn.isEnabled()  # «entiendo» still unchecked
    tab.takeover_confirm.setChecked(True)
    assert tab.apply_takeover_btn.isEnabled()
    tab._apply_takeover()
    assert applied == [(7, [5562])]

    # Any reload of the event invalidates the preview: no applying a stale list.
    tab._render_detail(map_detail(DETAIL_NODE))
    assert not tab.apply_takeover_btn.isEnabled()


def test_new_event_form_sends_local_date_and_times(tab):
    tab._start_new_event()
    tab.name_edit.setText("Evento nuevo")
    tab.end_unknown.setChecked(False)
    data = tab._form_data()
    assert data["name"] == "Evento nuevo" and data["venue_id"] == 1
    assert data["start_time"] == "19:00" and data["end_time"] == "20:00"
    assert data["capacity"] is None  # «Aún no sé el cupo» by default
    assert data["seat_ids"] == [11, 12, 13]
    assert len(data["local_date"]) == 10 and data["timezone"] == "America/Mexico_City"


# ---------------------------------------------------------------- clase extra (compensación por defecto)
_PREVIEW = "lun 02/11 19:00 · Bicicleta 1 · vence 02/11 (antes 01/11)"


def _detail_with(**displacement):
    node = dict(DETAIL_NODE)
    node["displacements"] = [dict(DETAIL_NODE["displacements"][0], **displacement)]
    return map_detail(node)


@pytest.mark.asyncio
async def test_extra_class_calls_name_the_client_and_the_event():
    applied = dict(DETAIL_NODE["displacements"][0], compensationType="membership_extension",
                   compensationNotes="Clase extra el lun 02/11 a las 19:00 en Bicicleta 1.",
                   followUpStatus="pending", bonusPreview=None, bonusBlocker=None)
    client = FakeClient([
        {"applyDisplacementBonusClass": {"success": True, "error": None, "displacement": applied}},
        {"applySpecialEventBonusClasses": {"success": True, "error": None,
                                           "message": "Clase extra para 1 cliente(s).", "detail": DETAIL_NODE}},
    ])
    service = SpecialEventsService(client)

    one = await service.apply_bonus_class(9, resolved=False)
    assert "applyDisplacementBonusClass" in client.calls[0][0]
    assert client.calls[0][1] == {"id": 9, "resolved": False}
    assert one["success"] and one["displacement"]["compensation_type"] == "membership_extension"

    bulk = await service.apply_bonus_classes(7)
    assert "applySpecialEventBonusClasses" in client.calls[1][0] and client.calls[1][1] == {"id": 7}
    assert bulk["message"] == "Clase extra para 1 cliente(s)." and bulk["detail"]["event"]["id"] == 7


def test_compensation_dialog_proposes_the_extra_class_first(qtbot):
    from PySide6.QtWidgets import QDialogButtonBox

    from app.views.tabs.special_events_tab import BONUS_CLASS, FollowUpDialog

    dialog = FollowUpDialog(None, mode="compensation", displacement={"bonus_preview": _PREVIEW})
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert dialog.type_combo.currentData() == BONUS_CLASS
    assert dialog.type_combo.currentText() == "Clase extra al terminar su membresía"
    assert _PREVIEW in dialog.hint.text() and ok.isEnabled()
    assert not dialog.notes_edit.isEnabled()  # the server writes what it did
    assert dialog.data() == {"compensation_type": BONUS_CLASS, "compensation_notes": None, "resolved": True}

    blocked = FollowUpDialog(None, mode="compensation",
                             displacement={"bonus_blocker": "No tiene membresía con la cual darle la clase extra."})
    qtbot.addWidget(blocked)
    ok = blocked.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert "No tiene membresía" in blocked.hint.text() and not ok.isEnabled()
    blocked.type_combo.setCurrentIndex(blocked.type_combo.findData("make_up_class"))
    assert ok.isEnabled() and blocked.notes_edit.isEnabled()


def test_registering_the_extra_class_applies_it_and_other_options_only_record(tab, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.views.tabs import special_events_tab as module

    tab._render_detail(_detail_with(bonusPreview=_PREVIEW))
    proposal = tab.displaced_table.item(0, 7)
    assert proposal.text() == "Propuesta: clase extra lun 02/11 19:00"
    assert proposal.toolTip() == f"Clase extra propuesta: {_PREVIEW}"
    tab.displaced_table.selectRow(0)
    calls = []
    monkeypatch.setattr(tab.controller, "apply_bonus_class",
                        lambda displacement_id, resolved=True: calls.append(("bonus", displacement_id, resolved)))
    monkeypatch.setattr(tab.controller, "update_follow_up", lambda payload: calls.append(("record", payload)))
    choice = {"code": None}

    class AcceptingDialog(module.FollowUpDialog):
        def exec(self):
            if choice["code"]:
                self.type_combo.setCurrentIndex(self.type_combo.findData(choice["code"]))
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(module, "FollowUpDialog", AcceptingDialog)
    tab._register_compensation()  # default option
    choice["code"] = "make_up_class"
    tab._register_compensation()
    assert calls[0] == ("bonus", 9, True)
    assert calls[1][0] == "record" and calls[1][1]["compensation_type"] == "make_up_class"


def test_an_extra_class_already_given_can_only_be_closed(tab, monkeypatch):
    from app.views.tabs import special_events_tab as module

    tab._render_detail(_detail_with(compensationType="membership_extension",
                                    compensationNotes="Clase extra el lun 02/11 a las 19:00."))
    tab.displaced_table.selectRow(0)
    asked, saved = [], []
    monkeypatch.setattr(module, "show_confirmation", lambda _parent, message, **_k: asked.append(message) or True)
    monkeypatch.setattr(tab.controller, "update_follow_up", saved.append)
    tab._register_compensation()
    assert "Ya se le dio la clase extra: Clase extra el lun 02/11" in asked[0]
    assert saved == [{"displacement_id": 9, "resolved": True}]


def test_bulk_extra_class_confirms_with_each_proposal(tab, monkeypatch):
    from app.views.tabs import special_events_tab as module

    tab._render_detail(_detail_with(bonusPreview=_PREVIEW))
    assert tab.bonus_all_btn.isEnabled()
    asked, applied = [], []
    monkeypatch.setattr(module, "show_confirmation", lambda _parent, message, **_k: asked.append(message) or True)
    monkeypatch.setattr(tab.controller, "apply_bonus_classes", applied.append)
    tab._apply_bonus_to_pending()
    assert applied == [7]
    assert f"• Omar Cortinas: {_PREVIEW}" in asked[0]

    tab._render_detail(_detail_with(bonusBlocker="No tiene membresía."))
    assert not tab.bonus_all_btn.isEnabled()
