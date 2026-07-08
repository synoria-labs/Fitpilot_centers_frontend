"""Unit tests for the pure subscription logic extracted from SubscriptionService.

These guard the behavior BEFORE any orchestration refactor of the QObject, and
confirm the delegating wrappers on SubscriptionService keep the same results.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.services import subscription_logic as sl
from app.services.subscription_service import SubscriptionService
from app.models.base import TimeslotGroup


# ---------------------------------------------------------------------------
# next_occurrence_on_or_after
# ---------------------------------------------------------------------------
def test_next_occurrence_same_weekday_returns_same_date():
    # 2026-07-06 is a Monday (isoweekday 1)
    d = date(2026, 7, 6)
    assert sl.next_occurrence_on_or_after(d, 1) == d


def test_next_occurrence_advances_to_target_weekday():
    monday = date(2026, 7, 6)
    # next Wednesday (3) on/after Monday is 2026-07-08
    assert sl.next_occurrence_on_or_after(monday, 3) == date(2026, 7, 8)
    # next Sunday (7) on/after Monday is 2026-07-12
    assert sl.next_occurrence_on_or_after(monday, 7) == date(2026, 7, 12)


def test_next_occurrence_wraps_to_next_week():
    wednesday = date(2026, 7, 8)
    # next Monday (1) on/after Wednesday is the following Monday 2026-07-13
    assert sl.next_occurrence_on_or_after(wednesday, 1) == date(2026, 7, 13)


def test_service_wrapper_matches_module():
    d = date(2026, 7, 6)
    assert SubscriptionService.next_occurrence_on_or_after(d, 5) == sl.next_occurrence_on_or_after(d, 5)


# ---------------------------------------------------------------------------
# validate_basic_form_data
# ---------------------------------------------------------------------------
def _valid_form():
    return {"amount": 100, "payment_method": "cash"}


def test_valid_form_passes():
    assert sl.validate_basic_form_data(_valid_form()) is None


@pytest.mark.parametrize("amount", [0, -5, "x", None])
def test_bad_amount_rejected(amount):
    form = {"amount": amount, "payment_method": "cash"}
    assert sl.validate_basic_form_data(form) == "Monto debe ser mayor a 0"


def test_missing_payment_method_rejected():
    assert sl.validate_basic_form_data({"amount": 50}) == "Método de pago requerido"


def test_invalid_payment_method_rejected():
    err = sl.validate_basic_form_data({"amount": 50, "payment_method": "bitcoin"})
    assert err and err.startswith("Método de pago inválido")


def test_payment_amount_alias_accepted():
    assert sl.validate_basic_form_data({"payment_amount": 20, "payment_method": "card"}) is None


def test_end_before_start_rejected():
    form = {
        "amount": 10, "payment_method": "cash",
        "start_date": date(2026, 7, 10), "end_date": date(2026, 7, 5),
    }
    assert sl.validate_basic_form_data(form) == "La fecha fin debe ser posterior a la fecha de inicio"


def test_nested_person_validation():
    form = {"amount": 10, "payment_method": "cash", "person": {"full_name": "A"}}
    assert sl.validate_basic_form_data(form) == "Nombre debe tener al menos 2 caracteres"


def test_service_wrapper_validate_matches_module():
    form = {"amount": 10, "payment_method": "cash"}
    assert SubscriptionService.validate_basic_form_data(form) is sl.validate_basic_form_data(form)  # both None


# ---------------------------------------------------------------------------
# validate person/subscription/timeslot
# ---------------------------------------------------------------------------
def test_validate_person_data():
    assert sl.validate_person_data({"full_name": "Ana Ruiz"}) is None
    assert sl.validate_person_data({"full_name": ""}) == "Nombre completo es requerido"
    assert sl.validate_person_data({"full_name": "Ana", "phone_number": "123"}) == "Teléfono debe tener al menos 8 dígitos"


def test_validate_subscription_data():
    assert sl.validate_subscription_data({"plan_id": 3}) is None
    assert sl.validate_subscription_data({"plan_id": 0}) == "Plan de membresía requerido"
    bad = {"plan_id": 1, "start_at": datetime(2026, 7, 10), "end_at": datetime(2026, 7, 1)}
    assert sl.validate_subscription_data(bad) == "Fecha de fin debe ser posterior a fecha de inicio"


def test_validate_timeslot_group():
    good = TimeslotGroup(key="k", class_type_name="Spin", venue_name="Sala 1",
                         instructor_name=None, start_time_local="08:00",
                         template_ids=[1], templates=[])
    assert sl.validate_timeslot_group(good) is None

    empty = TimeslotGroup(key="k", class_type_name="Spin", venue_name="Sala 1",
                          instructor_name=None, start_time_local="08:00",
                          template_ids=[], templates=[])
    assert sl.validate_timeslot_group(empty) == "Grupo de horario no contiene plantillas válidas"


# ---------------------------------------------------------------------------
# build_timeslot_groups / find_group_by_template_id
# ---------------------------------------------------------------------------
def _tpl(tid, ctid, venue, start, instr=None, ct_name="Spin", venue_name="Sala"):
    # build_timeslot_groups only reads attributes, so a duck-typed object suffices
    # and avoids depending on ClassTemplate's constructor.
    return SimpleNamespace(
        id=tid, class_type_id=ctid, venue_id=venue, start_time_local=start,
        instructor_id=instr, class_type_name=ct_name, venue_name=venue_name,
        instructor_name=None, weekday=1,
    )


def test_build_timeslot_groups_groups_by_slot():
    # two templates in the SAME slot (same ct/venue/time/instructor) -> one group;
    # a third in a different time -> its own group.
    a = _tpl(1, 10, 100, "08:00")
    b = _tpl(2, 10, 100, "08:00")  # same slot as a
    c = _tpl(3, 10, 100, "09:00")  # different time
    groups = sl.build_timeslot_groups([a, b, c])
    assert len(groups) == 2
    slot_08 = next(g for g in groups if g.start_time_local == "08:00")
    assert sorted(slot_08.template_ids) == [1, 2]


def test_find_group_by_template_id():
    a = _tpl(1, 10, 100, "08:00")
    c = _tpl(3, 10, 100, "09:00")
    groups = sl.build_timeslot_groups([a, c])
    found = sl.find_group_by_template_id(3, groups)
    assert found is not None and 3 in found.template_ids
    assert sl.find_group_by_template_id(999, groups) is None


def test_service_wrapper_build_matches_module():
    a = _tpl(1, 10, 100, "08:00")
    via_service = SubscriptionService.build_timeslot_groups([a])
    via_module = sl.build_timeslot_groups([a])
    assert len(via_service) == len(via_module) == 1
    assert via_service[0].template_ids == via_module[0].template_ids
