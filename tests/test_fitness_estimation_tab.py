"""Humo de la pestaña de Estimaciones, con Qt real en modo offscreen.

La pantalla decide el número que las campañas le mandan al socio por WhatsApp, así que lo
que se comprueba aquí es que refleje fielmente lo que el backend devuelve: que una celda
vacía signifique «hereda el default» y no «cero», que el horario deducido se lea tal cual, y
que el ejemplo muestre los pasos intermedios en vez de sólo el total.

``FitnessEstimationTab`` se construye con el contenedor de dependencias stubbeado, igual que
el resto de las vistas de configuración: montarlo con un servicio real probaría el
contenedor, no la vista.
"""
from __future__ import annotations

import pytest

from app.services.fitness_estimation_service import (
    _map_class_types,
    _map_config,
    _map_preview,
    _map_schedule,
    _map_settings,
)


SETTINGS_NODE = {
    "config": {
        "id": 1,
        "referenceWeightKg": 70.0,
        "horizonWeeks": 104,
        "defaultSessionsPerWeek": 2.5,
        "minBookingsForHistory": 4,
        "cadenceLookbackDays": 180,
        "defaultMet": 6.0,
        "defaultDurationMin": 60,
        "defaultOpenDaysPerWeek": 5,
        "netOfResting": True,
        "kcalPerKgFat": 7700,
        "metabolicAdaptation": True,
        "kgHalfLifeDays": 365,
        "kgPer100KcalPerDay": 4.5,
        "realizationFactor": 1.0,
    },
    "classTypes": [
        {
            "id": 1, "code": "spinning", "name": "Spinning",
            "metValue": None, "effectiveMet": 8.5, "isDefault": True,
        },
        {
            "id": 2, "code": "yoga", "name": "Yoga",
            "metValue": 3.5, "effectiveMet": 3.5, "isDefault": False,
        },
    ],
    "schedule": {
        "openDaysPerWeek": 5,
        "openWeekdays": [1, 2, 3, 4, 5],
        "meanDurationMin": 60,
        "activeTemplates": 30,
    },
    "preview": {
        "daysInactive": 365, "weeksCounted": 52.1, "horizonReached": False,
        "sessionsPerWeek": 2.5, "sessionsMissed": 130.0, "met": 8.5, "durationMin": 60,
        "kcalPerSession": 525.0, "kcalPerDay": 187.5, "kcal": 68250,
        "kgSteadyState": 8.44, "kgFat": 4.22,
        "kcalText": "68,200", "kgFatText": "4.2", "windowLabel": "los últimos 12 meses",
    },
}


@pytest.fixture
def tab(qtbot, monkeypatch):
    from app.core import container
    from app.views.tabs import fitness_estimation_tab as module

    # Sin servicio el controller emite error al construir, y la vista lo enseña en un
    # QMessageBox modal — que en offscreen se queda esperando un click que nunca llega.
    # Los diálogos se anulan antes de instanciar, no después.
    monkeypatch.setattr(module, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(module, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(container, "get", lambda _name: None)

    widget = module.FitnessEstimationTab()
    qtbot.addWidget(widget)
    return widget


# ---------------------------------------------------------------- mapeo
def test_settings_mapping_round_trips_the_server_payload():
    mapped = _map_settings(SETTINGS_NODE)
    assert mapped["config"]["horizon_weeks"] == 104
    assert mapped["config"]["metabolic_adaptation"] is True
    assert mapped["schedule"]["open_days_per_week"] == 5
    assert mapped["preview"]["kcal_text"] == "68,200"
    assert mapped["preview"]["kg_steady_state"] == 8.44
    assert len(mapped["class_types"]) == 2


def test_an_inherited_met_maps_to_none_not_zero():
    """Null significa «hereda el default de la actividad». Convertirlo en 0 escribiría un
    override de cero MET en la siguiente guardada."""
    mapped = _map_class_types(SETTINGS_NODE["classTypes"])
    assert mapped[0]["met_value"] is None
    assert mapped[0]["effective_met"] == 8.5
    assert mapped[0]["is_default"] is True
    assert mapped[1]["met_value"] == 3.5


def test_an_empty_schedule_maps_to_zero_days_not_a_crash():
    assert _map_schedule(None)["open_days_per_week"] == 0
    assert _map_schedule({})["open_weekdays"] == []
    assert _map_preview(None) is None
    assert _map_config(None) is None


# ---------------------------------------------------------------- widget
def test_tab_builds_and_renders_the_settings(tab):
    tab._apply_settings(_map_settings(SETTINGS_NODE))

    assert tab.weight_spin.value() == pytest.approx(70.0)
    assert tab.horizon_spin.value() == 104
    assert tab.net_check.isChecked() is True
    assert tab.intensity_table.rowCount() == 2


def test_the_derived_schedule_is_shown_in_words(tab):
    """Un operador que ve un número raro tiene que poder distinguir «falta configurar algo»
    de «falta cargar el horario»."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))

    text = tab.schedule_days_label.text()
    assert "5 por semana" in text
    assert "lunes" in text and "viernes" in text
    assert "sábado" not in text
    assert tab.schedule_duration_label.text() == "60 min"


def test_a_gym_without_a_schedule_says_so_instead_of_showing_zero(tab):
    empty = dict(SETTINGS_NODE)
    empty["schedule"] = {"openDaysPerWeek": 0, "openWeekdays": [], "meanDurationMin": None,
                         "activeTemplates": 0}
    tab._apply_settings(_map_settings(empty))
    assert "sin horario cargado" in tab.schedule_days_label.text()
    assert tab.schedule_duration_label.text() == "sin horario cargado"


def test_inherited_met_shows_the_value_in_force_and_marks_it(tab):
    """Un catálogo sin tocar no debe verse «sin configurar»: la celda propia va vacía pero
    la columna en uso muestra 8.5."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))

    assert tab.intensity_table.item(0, 1).text() == ""
    assert "8.5" in tab.intensity_table.item(0, 2).text()
    assert "por defecto" in tab.intensity_table.item(0, 2).text()
    assert tab.intensity_table.item(1, 1).text() == "3.5"
    assert "por defecto" not in tab.intensity_table.item(1, 2).text()


def test_repainting_the_table_does_not_fire_a_save_per_row(tab, monkeypatch):
    """El handler de celda escribe al backend; sin el guard, repintar la tabla con la
    respuesta del servidor dispararía una guardada por fila, en bucle."""
    calls = []
    monkeypatch.setattr(
        tab.controller, "set_class_type_met", lambda *a, **k: calls.append(a)
    )
    tab._apply_settings(_map_settings(SETTINGS_NODE))
    assert calls == []


def test_the_example_shows_the_intermediate_steps(tab):
    """«130 clases x 525 kcal» se puede verificar; «68,200» sólo se puede creer."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))

    headline = tab.preview_headline.text()
    assert "68,200" in headline and "4.2" in headline
    assert "los últimos 12 meses" in headline

    detail = tab.preview_detail.text()
    assert "130 clases perdidas" in detail
    assert "525 kcal" in detail
    assert "8.5 MET" in detail
    assert "60 min" in detail


def test_the_example_names_the_ceiling_the_estimate_approaches(tab):
    """Sin el techo, la cifra de kg se lee como si creciera para siempre — que es justo la
    intuición equivocada que el modelo saturante corrige."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))

    detail = tab.preview_detail.text()
    assert "188 kcal/día" in detail
    assert "8.4 kg" in detail
    assert "no pasa de ahí" in detail


def test_a_biting_horizon_is_called_out(tab):
    """Un tope que muerde reproduce el bug original: todos los socios más viejos reciben el
    mismo número. La pantalla tiene que decirlo, no esconderlo."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))
    assert "mordiendo" not in tab.preview_detail.text()

    capped = dict(SETTINGS_NODE)
    capped["preview"] = {**SETTINGS_NODE["preview"], "horizonReached": True}
    tab._apply_settings(_map_settings(capped))
    assert "mordiendo" in tab.preview_detail.text()


def test_only_the_active_kg_model_stays_editable(tab):
    """Los dos modelos usan parámetros distintos; dejar los dos habilitados sugiere que
    ambos cuentan."""
    tab._apply_settings(_map_settings(SETTINGS_NODE))
    assert tab.half_life_spin.isEnabled() is True
    assert tab.kg_per_100_spin.isEnabled() is True
    assert tab.kcal_per_kg_spin.isEnabled() is False

    linear = dict(SETTINGS_NODE)
    linear["config"] = {**SETTINGS_NODE["config"], "metabolicAdaptation": False}
    tab._apply_settings(_map_settings(linear))
    assert tab.half_life_spin.isEnabled() is False
    assert tab.kcal_per_kg_spin.isEnabled() is True


def test_save_sends_the_adaptation_parameters(tab, monkeypatch):
    sent = {}
    monkeypatch.setattr(tab.controller, "save_config", lambda d: sent.update(d))
    tab._apply_settings(_map_settings(SETTINGS_NODE))
    tab._save_config()

    assert sent["metabolic_adaptation"] is True
    assert sent["kg_half_life_days"] == 365
    assert sent["kg_per_100_kcal_per_day"] == pytest.approx(4.5)
    assert sent["horizon_weeks"] == 104
