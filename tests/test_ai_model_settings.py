from types import SimpleNamespace

import pytest

from app.services.chatbot_config_service import ChatbotConfigService
from app.views.widgets.ai_model_combo import AiModelCombo, DEFAULT_AI_MODEL


class Client:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def execute(self, query, variables=None, **kwargs):
        self.calls.append((query, variables))
        return self.results.pop(0)


def test_model_selector_uses_ids_and_preserves_custom_choices(qtbot):
    combo = AiModelCombo()
    qtbot.addWidget(combo)
    assert combo.currentText() == "Claude Sonnet 5.5"
    assert combo.model_id() == DEFAULT_AI_MODEL
    combo.set_model("claude-custom-future")
    combo.set_options([{"id": DEFAULT_AI_MODEL, "label": "Sonnet 5.5"}])
    assert combo.model_id() == "claude-custom-future"
    combo.setEditText("claude-custom-entered")
    assert combo.model_id() == "claude-custom-entered"


@pytest.mark.asyncio
async def test_chatbot_service_roundtrips_all_models_and_catalog():
    node = {"id": 1, "model": DEFAULT_AI_MODEL, "templateAiModel": "claude-haiku-4-5",
            "promptOptimizerModel": "claude-opus-5-5"}
    client = Client([{"chatbotConfig": node, "aiModelOptions": [{"id": DEFAULT_AI_MODEL, "label": "Sonnet"}]},
                     {"saveChatbotConfig": {"success": True, "config": node}}])
    service = ChatbotConfigService(client)
    result = await service.get_config()
    assert result["template_ai_model"] == "claude-haiku-4-5"
    assert result["model_options"][0]["id"] == DEFAULT_AI_MODEL
    await service.save_config(enabled=True, require_confirmation=True, require_mp_payment=True,
        model=DEFAULT_AI_MODEL, system_prompt="Hola", template_ai_model="claude-haiku-4-5", prompt_optimizer_model="claude-opus-5-5")
    sent = client.calls[-1][1]["input"]
    assert sent["templateAiModel"] == "claude-haiku-4-5" and sent["promptOptimizerModel"] == "claude-opus-5-5"


def test_chatbot_ui_saves_three_independent_models(qtbot, monkeypatch):
    from app.views.tabs import chatbot_config_tab as module

    monkeypatch.setattr(module.container, "get", lambda key: object())
    monkeypatch.setattr(module.ChatbotConfigController, "load_config", lambda self: None)
    tab = module.ChatbotConfigTab()
    qtbot.addWidget(tab)
    tab._on_config_loaded({"model": DEFAULT_AI_MODEL, "template_ai_model": "claude-haiku-4-5",
                           "prompt_optimizer_model": "claude-opus-5-5"})
    saved = []
    monkeypatch.setattr(tab.controller, "save_config", saved.append)
    tab._on_save_clicked()
    assert saved[0]["model"] == DEFAULT_AI_MODEL
    assert saved[0]["template_ai_model"] == "claude-haiku-4-5"
    assert saved[0]["prompt_optimizer_model"] == "claude-opus-5-5"


def test_admin_ui_preserves_backend_selected_model(qtbot, monkeypatch):
    from app.views.tabs import owner_agent_config_tab as module

    monkeypatch.setattr(module.container, "get", lambda key: object())
    monkeypatch.setattr(module.OwnerAgentConfigController, "load_bundle", lambda self: None)
    tab = module.OwnerAgentConfigTab()
    qtbot.addWidget(tab)
    tab._apply_config({"model": "claude-admin-custom"})
    saved = []
    monkeypatch.setattr(tab.controller, "save_config", saved.append)
    tab._save_config()
    assert saved[0]["model"] == "claude-admin-custom"
