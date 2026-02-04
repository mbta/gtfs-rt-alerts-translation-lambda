from typing import Any

import httpx
import pytest

from gtfs_translation.core.smartling import SmartlingTranslator


@pytest.mark.asyncio
async def test_smartling_auth_caching(respx_mock: Any) -> None:
    # Mock auth endpoint
    auth_route = respx_mock.post("https://api.smartling.com/auth-api/v2/authenticate").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"accessToken": "test-token", "expiresIn": 3600}}}
        )
    )

    # Mock translate endpoint
    trans_route = respx_mock.post(
        "https://api.smartling.com/mt-router-api/v2/accounts/acc123/smartling-mt"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "data": {"items": [{"key": "0", "translationText": "Hola", "provider": "test"}]}
                }
            },
        )
    )

    translator = SmartlingTranslator("user", "secret", "acc123")

    # First call: Auth + Translate
    res1 = translator.translate_batch(["Hello"], ["es"])
    assert res1 == {"es": ["Hola"]}
    assert auth_route.call_count == 1
    assert trans_route.call_count == 1

    # Second call: Should use cached token
    res2 = translator.translate_batch(["Hello"], ["es"])
    assert res2 == {"es": ["Hola"]}
    assert auth_route.call_count == 1  # Still 1
    assert trans_route.call_count == 2

    await translator.close()


@pytest.mark.asyncio
async def test_smartling_auth_retry_on_401(respx_mock: Any) -> None:
    # Mock auth endpoint (returns same token)
    respx_mock.post("https://api.smartling.com/auth-api/v2/authenticate").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"accessToken": "new-token", "expiresIn": 3600}}}
        )
    )

    # Mock translate endpoint to fail first with 401, then succeed
    trans_route = respx_mock.post(
        "https://api.smartling.com/mt-router-api/v2/accounts/acc123/smartling-mt"
    )
    trans_route.side_effect = [
        httpx.Response(401),
        httpx.Response(
            200,
            json={
                "response": {
                    "data": {
                        "items": [
                            {"key": "0", "translationText": "Retry Success", "provider": "test"}
                        ]
                    }
                }
            },
        ),
    ]

    translator = SmartlingTranslator("user", "secret", "acc123")
    # Pre-set a "stale" token
    translator._token = "stale"
    translator._token_expiry = 9999999999

    res = translator.translate_batch(["Hello"], ["es"])
    assert res == {"es": ["Retry Success"]}
    assert trans_route.call_count == 2

    await translator.close()

@pytest.mark.asyncio
async def test_smartling_file_translator(respx_mock: Any) -> None:
    from gtfs_translation.core.smartling import SmartlingFileTranslator

    # Mock auth endpoint
    respx_mock.post("https://api.smartling.com/auth-api/v2/authenticate").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"accessToken": "test-token", "expiresIn": 3600}}}
        )
    )

    # Mock file translate endpoint
    trans_route = respx_mock.post(
        "https://api.smartling.com/mt-router-api/v2/accounts/acc123/smartling-mt/file"
    ).mock(
        return_value=httpx.Response(200, json=["Hola", "Mundo"])
    )

    translator = SmartlingFileTranslator("user", "secret", "acc123")
    res = translator.translate_batch(["Hello", "World"], ["es"])
    
    assert res == {"es": ["Hola", "Mundo"]}
    assert trans_route.call_count == 1
    
    # Check that we sent a multipart request with the right fields
    call = trans_route.calls[0]
    assert "multipart/form-data" in call.request.headers["content-type"]
    
    await translator.close()
