from typing import Any

import httpx
import pytest

from gtfs_translation.core.smartling import SmartlingJobBatchesTranslator


@pytest.mark.asyncio
async def test_job_batches_translator_success(respx_mock: Any) -> None:
    # Auth
    respx_mock.post("https://api.smartling.com/auth-api/v2/authenticate").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"accessToken": "test-token", "expiresIn": 3600}}}
        )
    )

    # Job
    respx_mock.post("https://api.smartling.com/job-batches-api/v2/projects/proj123/jobs").mock(
        return_value=httpx.Response(
            200, json={"response": {"data": {"translationJobUid": "job123"}}}
        )
    )

    # Batch
    respx_mock.post("https://api.smartling.com/job-batches-api/v2/projects/proj123/batches").mock(
        return_value=httpx.Response(200, json={"response": {"data": {"batchUid": "batch123"}}})
    )

    # Upload
    respx_mock.post(
        "https://api.smartling.com/job-batches-api/v2/projects/proj123/batches/batch123/file"
    ).mock(return_value=httpx.Response(202, json={"response": {"code": "ACCEPTED"}}))

    # Status
    respx_mock.get(
        "https://api.smartling.com/job-batches-api/v2/projects/proj123/batches/batch123"
    ).mock(return_value=httpx.Response(200, json={"response": {"data": {"status": "COMPLETED"}}}))

    # Download
    respx_mock.get("https://api.smartling.com/files-api/v2/projects/proj123/locales/es/file").mock(
        return_value=httpx.Response(200, json=["Hola"])
    )

    translator = SmartlingJobBatchesTranslator("user", "secret", "proj123", "s3://bucket/key.json")
    res = await translator.translate_batch(["Hello"], ["es"])

    assert res == {"es": ["Hola"]}
    await translator.close()
