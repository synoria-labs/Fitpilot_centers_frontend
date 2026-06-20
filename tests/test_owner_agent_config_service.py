from __future__ import annotations

import pytest

from app.services.owner_agent_config_service import OwnerAgentConfigService


class _FakeGraphQLClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def execute(self, query, variables=None, use_auth=True):
        self.calls.append({"query": query, "variables": variables, "use_auth": use_auth})
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_owner_agent_config_bundle_maps_camel_case():
    client = _FakeGraphQLClient(
        [
            {
                "ownerAgentConfig": {
                    "id": 1,
                    "enabled": True,
                    "requireConfirmation": True,
                    "model": "claude-test",
                    "systemPrompt": "Admin prompt",
                    "historyLimit": 25,
                    "maxTokens": 900,
                    "serverEnabled": False,
                },
                "ownerAgentAuthorizedPhones": [
                    {
                        "id": 7,
                        "label": "Dueno",
                        "phoneNumber": "8719708890",
                        "normalizedWaId": "5218719708890",
                        "enabled": True,
                        "createdBy": 2,
                    }
                ],
            }
        ]
    )

    bundle = await OwnerAgentConfigService(client).get_config_bundle()

    assert bundle["config"]["enabled"] is True
    assert bundle["config"]["require_confirmation"] is True
    assert bundle["config"]["server_enabled"] is False
    assert bundle["config"]["history_limit"] == 25
    assert bundle["phones"][0]["normalized_wa_id"] == "5218719708890"


@pytest.mark.asyncio
async def test_save_owner_agent_config_sends_expected_input_shape():
    client = _FakeGraphQLClient(
        [
            {
                "saveOwnerAgentConfig": {
                    "success": True,
                    "error": None,
                    "config": {
                        "id": 1,
                        "enabled": True,
                        "requireConfirmation": False,
                        "model": "claude-test",
                        "systemPrompt": "Prompt",
                        "historyLimit": 40,
                        "maxTokens": 1200,
                        "serverEnabled": True,
                    },
                }
            }
        ]
    )

    result = await OwnerAgentConfigService(client).save_config(
        enabled=True,
        require_confirmation=False,
        model="claude-test",
        system_prompt="Prompt",
        history_limit=40,
        max_tokens=1200,
    )

    sent = client.calls[0]["variables"]["input"]
    assert sent == {
        "enabled": True,
        "requireConfirmation": False,
        "model": "claude-test",
        "systemPrompt": "Prompt",
        "historyLimit": 40,
        "maxTokens": 1200,
    }
    assert result["success"] is True
    assert result["config"]["max_tokens"] == 1200
