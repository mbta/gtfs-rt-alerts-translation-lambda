from typing import Any

import httpx
import pytest

from gtfs_translation.core.smartling import SmartlingFileTranslator, SmartlingTranslator


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
    res1 = await translator.translate_batch(["Hello"], ["es"])
    assert res1 == {"es": ["Hola"]}
    assert auth_route.call_count == 1
    assert trans_route.call_count == 1

    # Second call: Should use cached token
    res2 = await translator.translate_batch(["Hello"], ["es"])
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

    res = await translator.translate_batch(["Hello"], ["es"])
    assert res == {"es": ["Retry Success"]}
    assert trans_route.call_count == 2

    await translator.close()


@pytest.mark.asyncio
async def test_smartling_file_translator(respx_mock: Any) -> None:
    # Mock auth endpoint
    respx_mock.post("https://api.smartling.com/auth-api/v2/authenticate").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"accessToken": "test-token", "expiresIn": 3600}}}
        )
    )

    # Mock file upload
    upload_route = respx_mock.post(
        "https://api.smartling.com/file-translations-api/v2/accounts/acc123/files"
    ).mock(return_value=httpx.Response(200, json={"response": {"data": {"fileUid": "file123"}}}))

    # Mock MT start
    mt_start_route = respx_mock.post(
        "https://api.smartling.com/file-translations-api/v2/accounts/acc123/files/file123/mt"
    ).mock(return_value=httpx.Response(200, json={"response": {"data": {"mtUid": "mt123"}}}))

    # Mock status check (first IN_PROGRESS, then COMPLETED)
    status_route = respx_mock.get(
        "https://api.smartling.com/file-translations-api/v2/accounts/acc123/files/file123/mt/mt123/status"
    )
    status_route.side_effect = [
        httpx.Response(200, json={"response": {"data": {"status": "IN_PROGRESS"}}}),
        httpx.Response(200, json={"response": {"data": {"status": "COMPLETED"}}}),
    ]

    # Mock download
    dl_route = respx_mock.get(
        "https://api.smartling.com/file-translations-api/v2/accounts/acc123/files/file123/mt/mt123/locales/es/file"
    ).mock(return_value=httpx.Response(200, json=["Hola", "Mundo"]))

    translator = SmartlingFileTranslator("user", "secret", "acc123")
    res = await translator.translate_batch(["Hello", "World"], ["es"])

    assert res == {"es": ["Hola", "Mundo"]}
    assert upload_route.call_count == 1
    assert mt_start_route.call_count == 1
    assert status_route.call_count == 2
    assert dl_route.call_count == 1

    await translator.close()
