"""Humo de los widgets del asistente de campañas, con Qt real en modo offscreen.

No prueban lógica de negocio: comprueban que cada widget se construye, acepta los datos que
el controller le pasa y responde a las llamadas que hace la pestaña. Es lo que atrapa el
fallo más probable de un refactor de UI — un widget que revienta al abrirse — y lo que las
comprobaciones estáticas no pueden ver.

``CampaignsTab`` queda fuera a propósito: exige el contenedor de dependencias con un
``campaigns_service`` real, y montarlo aquí probaría el contenedor, no la vista.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from app.views.tabs.campaigns.panels import (
    MetricsPanel,
    RecipientsTable,
    recipient_status_label,
    skip_reason_label,
)
from app.views.tabs.campaigns.steps import AudienceStep, MessageStep, ReviewStep


@pytest.fixture(autouse=True)
def _stub_media_loader(monkeypatch):
    """MessageStep's preview now passes real-looking media_url values through to
    TemplatePreviewWidget, which schedules an async fetch via the app's AsyncioExecutor — not
    running in this headless test process. Left unstubbed, the fetch fails after several
    seconds and its deferred callback can fire once qtbot has already torn the widget down
    (a QLabel access on a deleted C++ object). None of these are network tests, so stub the
    loader: a bare MediaFetchHandle whose signals are simply never emitted."""
    from app.services.media_loader import MediaFetchHandle

    class _StubLoader:
        def cached_path(self, url):  # noqa: ARG002 - matches MediaLoader's signature
            return None

        def fetch(self, url, *, force=False):  # noqa: ARG002
            return MediaFetchHandle()

    monkeypatch.setattr(
        "app.views.tabs.whatsapp.template_preview_widget.get_media_loader",
        lambda: _StubLoader(),
    )


OBJECTIVES = [{"key": "win_back", "label": "Reactivación"}]
VARIABLES = [
    {"key": "member_first_name", "label": "Primer nombre", "sample": "Juan"},
    {"key": "favorite_class_name", "label": "Clase habitual", "sample": "Spinning"},
]
TEMPLATES = [
    {
        "id": 5,
        "template_name": "winback_v1",
        "components": [
            {"type": "BODY", "text": "Hola {{1}}, te extrañamos en {{2}}."},
            {"type": "FOOTER", "text": "FitPilot"},
        ],
    }
]
IMAGE_TEMPLATE_WITH_DEFAULT = {
    "id": 6,
    "template_name": "promo_con_default",
    "default_header_media_asset_id": 101,
    "components": [
        {"type": "HEADER", "format": "IMAGE"},
        {"type": "BODY", "text": "Hola {{1}}."},
    ],
}
IMAGE_TEMPLATE_WITHOUT_DEFAULT = {
    "id": 7,
    "template_name": "promo_sin_default",
    "default_header_media_asset_id": None,
    "components": [
        {"type": "HEADER", "format": "IMAGE"},
        {"type": "BODY", "text": "Hola {{1}}."},
    ],
}
IMAGE_ASSETS = [
    {"id": 101, "display_name": "Banner promo", "public_url": "https://cdn.example/101.jpg"},
    {"id": 102, "display_name": "Banner alterno", "public_url": "https://cdn.example/102.jpg"},
]
PLANS = [{"id": 1, "name": "Mensualidad"}]
CLASS_TYPES = [{"id": 7, "name": "Spinning"}]
CLASS_TEMPLATES = [
    {
        "id": 11, "class_type_id": 7, "class_type_name": "Spinning", "weekday": 1,
        "start_time_local": "08:00:00", "instructor_id": None, "instructor_name": None,
        "name": None, "is_active": True,
    }
]


@pytest.fixture
def audience(qtbot) -> AudienceStep:
    step = AudienceStep()
    qtbot.addWidget(step)
    step.set_objectives(OBJECTIVES)
    step.set_plans(PLANS)
    step.set_classes(CLASS_TYPES, CLASS_TEMPLATES)
    return step


def test_audience_step_builds_a_usable_spec(audience):
    """El paso 1 arranca con la audiencia win-back por defecto."""
    spec = audience.audience_spec()

    assert spec["base"] == "members"
    kinds = {p["type"] for p in spec["predicates"]}
    assert "membership_status" in kinds
    assert "membership_end_at" in kinds


def test_expiry_range_is_shown_forwards_and_sent_as_offsets(audience):
    """La UI dice 'hace 90 días'; la API espera -90."""
    audience.end_min_spin.setValue(90)
    audience.end_max_spin.setValue(7)

    predicate = next(
        p for p in audience.audience_spec()["predicates"] if p["type"] == "membership_end_at"
    )
    assert predicate["days_from_now"] == [-90, -7]


def test_audience_spec_round_trips(audience):
    audience.class_picker._type_chips[7].setChecked(True)
    spec = audience.audience_spec()

    audience.apply_audience_spec(spec)

    assert audience.audience_spec() == spec


def test_affinity_mode_is_a_segmented_control(audience):
    """Exactamente un modo activo a la vez."""
    audience._set_affinity_mode("attended")
    assert audience._affinity_mode() == "attended"
    assert sum(chip.isChecked() for chip in audience.mode_chips.values()) == 1

    audience._set_affinity_mode("favorite")
    assert audience._affinity_mode() == "favorite"


def test_message_step_renders_the_template_with_sample_values(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates(TEMPLATES)

    step.select_template(5, ["member_first_name", "favorite_class_name"])

    assert step.template_id() == 5
    assert step.param_mapping() == ["member_first_name", "favorite_class_name"]


def test_message_step_warns_when_a_class_variable_may_be_blank(qtbot):
    """Un socio sin historial recibiría ese hueco vacío; mejor avisar antes de enviar."""
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates(TEMPLATES)

    step.select_template(5, ["member_first_name", "favorite_class_name"])
    assert not step.warning_label.isHidden()

    step.select_template(5, ["member_first_name", "member_first_name"])
    assert step.warning_label.isHidden()


def test_message_step_without_a_template_does_not_crash(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([])

    assert step.template_id() is None
    assert step.param_mapping() == []


def test_media_section_hidden_for_a_text_only_template(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates(TEMPLATES)
    step.select_template(5, [])

    assert step.media_container.isHidden()


def test_media_section_shown_for_an_image_header_template(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITH_DEFAULT])
    step.select_template(6, [])

    assert not step.media_container.isHidden()


@pytest.mark.parametrize(
    "mode,setup,expected",
    [
        ("default", lambda step: None, {"headerMediaAssetId": None, "headerMediaUrl": None}),
        (
            "asset",
            lambda step: step.media_asset_combo.setCurrentIndex(
                step.media_asset_combo.findData(102)
            ),
            {"headerMediaAssetId": 102, "headerMediaUrl": None},
        ),
        (
            "url",
            lambda step: step.media_url_input.setText("https://cdn.example/manual.jpg"),
            {"headerMediaAssetId": None, "headerMediaUrl": "https://cdn.example/manual.jpg"},
        ),
    ],
)
def test_header_media_override_resolves_per_mode(qtbot, mode, setup, expected):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITH_DEFAULT])
    step.select_template(6, [])
    step.set_media_assets("image", IMAGE_ASSETS)

    step.media_mode.setCurrentIndex(step.media_mode.findData(mode))
    setup(step)

    assert step.header_media_override() == expected


def test_set_media_override_restores_asset_mode(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITH_DEFAULT])
    step.select_template(6, [])
    step.set_media_assets("image", IMAGE_ASSETS)

    step.set_media_override(102, None)

    assert step.media_mode.currentData() == "asset"
    assert step.media_asset_combo.currentData() == 102


def test_set_media_override_restores_url_mode(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITH_DEFAULT])
    step.select_template(6, [])

    step.set_media_override(None, "https://cdn.example/manual.jpg")

    assert step.media_mode.currentData() == "url"
    assert step.media_url_input.text() == "https://cdn.example/manual.jpg"


def test_media_warning_when_template_needs_media_and_has_no_default(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITHOUT_DEFAULT])
    step.select_template(7, [])

    assert not step.warning_label.isHidden()
    assert "requiere una imagen" in step.warning_label.text()


def test_no_media_warning_when_template_already_has_a_default(qtbot):
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates([IMAGE_TEMPLATE_WITH_DEFAULT])
    step.select_template(6, [])

    assert step.warning_label.isHidden()


def test_message_step_shows_the_full_catalog_without_scrolling(qtbot):
    """Qt's QComboBox defaults to 10 visible rows; the real catalog has 15 variables."""
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(VARIABLES)
    step.set_templates(TEMPLATES)
    step.select_template(5, [])

    combo = step._param_combos[0]
    assert combo.maxVisibleItems() >= len(VARIABLES)


def test_message_step_sets_variable_description_as_a_tooltip(qtbot):
    variables = VARIABLES + [
        {
            "key": "kg_fat_equivalent",
            "label": "Kg de grasa",
            "sample": "1.1",
            "description": "Estimación, no el peso real del socio.",
        }
    ]
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(variables)
    step.set_templates(TEMPLATES)
    step.select_template(5, [])

    combo = step._param_combos[0]
    index = combo.findData("kg_fat_equivalent")
    assert index >= 0
    assert combo.itemData(index, Qt.ItemDataRole.ToolTipRole) == (
        "Estimación, no el peso real del socio."
    )


def test_message_step_warns_specifically_about_schedule_variables(qtbot):
    """Day/time/schedule blank out more often than the class name — a distinct caveat."""
    step = MessageStep()
    qtbot.addWidget(step)
    step.set_variables(
        VARIABLES + [{"key": "favorite_class_day", "label": "Día de esa clase", "sample": "lunes"}]
    )
    step.set_templates(TEMPLATES)

    step.select_template(5, ["member_first_name", "favorite_class_day"])
    assert not step.warning_label.isHidden()
    assert "reserva fija" in step.warning_label.text()
    assert "Quien no tenga historial" not in step.warning_label.text()


def test_review_step_reports_its_schedule_choice(qtbot):
    step = ReviewStep()
    qtbot.addWidget(step)
    step.set_summary(["Audiencia: 74 recibirán", "Plantilla: winback_v1"])

    assert step.is_scheduled() is False   # "Enviar ahora" por defecto
    step.schedule_radio.setChecked(True)
    assert step.is_scheduled() is True
    assert step.scheduled_at() is not None


def test_metrics_panel_shows_and_clears(qtbot):
    panel = MetricsPanel()
    qtbot.addWidget(panel)

    panel.set_metrics(
        {
            "targeted": 100, "sent": 80, "delivered": 70, "read": 40, "replied": 5,
            "converted": 12, "revenue_recovered": 6000.0, "pending": 20,
            "delivery_rate": 0.875, "read_rate": 0.5, "conversion_rate": 0.15,
        },
        sending=True,
    )
    assert not panel.progress.isHidden()
    assert panel.progress.maximum() == 100

    panel.clear()
    assert panel.progress.isHidden()


def test_recipients_table_explains_why_someone_was_skipped(qtbot):
    table = RecipientsTable()
    qtbot.addWidget(table)
    table.set_class_names({7: "Spinning"})
    table.set_recipients(
        [
            {"phone_e164": "5218719708890", "status": "sent", "favorite_class_type_id": 7},
            {"phone_e164": None, "status": "skipped", "skip_reason": "no_phone"},
            {"phone_e164": "521871970889", "status": "failed", "error": "Meta 131047"},
        ]
    )

    assert table.table.rowCount() == 3
    assert table.table.item(0, 3).text() == "Spinning"
    assert table.table.item(1, 2).text() == "sin número de WhatsApp"
    assert table.table.item(2, 2).text() == "Meta 131047"   # el error gana al motivo


def test_status_and_skip_labels_never_return_raw_codes():
    assert recipient_status_label("opted_out") == "Sin consentimiento"
    assert skip_reason_label("recency_block") == "contactado hace poco"
    assert skip_reason_label(None) == ""
    # Un código que no conocemos se muestra tal cual, en vez de desaparecer.
    assert skip_reason_label("motivo_nuevo") == "motivo_nuevo"
