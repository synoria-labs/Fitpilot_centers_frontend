"""Model selector shared by all AI settings; backend options preserve custom IDs."""
from PySide6.QtWidgets import QComboBox

DEFAULT_AI_MODEL = "claude-sonnet-5-5"
_FALLBACK_OPTIONS = [
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"},
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5"},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5"},
]


class AiModelCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setToolTip("Selecciona un modelo o escribe su identificador de Claude.")
        self.set_options(_FALLBACK_OPTIONS)
        self.set_model(DEFAULT_AI_MODEL)

    def model_id(self):
        index = self.currentIndex()
        if index >= 0 and self.currentText() == self.itemText(index):
            return self.itemData(index) or DEFAULT_AI_MODEL
        return self.currentText().strip() or DEFAULT_AI_MODEL

    def set_model(self, model):
        model = model or DEFAULT_AI_MODEL
        index = self.findData(model)
        if index < 0:
            self.addItem(model, model)
            index = self.count() - 1
        self.setCurrentIndex(index)

    def set_options(self, options):
        if not options:
            return
        selected = self.model_id()
        self.blockSignals(True)
        self.clear()
        for option in options:
            if option.get("id"):
                self.addItem(option.get("label") or option["id"], option["id"])
        self.set_model(selected)
        self.blockSignals(False)
