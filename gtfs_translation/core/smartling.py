import asyncio
import json
import logging
import random
import time

import httpx

from gtfs_translation.core.translator import Translator


class SmartlingTranslator(Translator):
    _token: str | None = None
    _token_expiry: float = 0

    def __init__(self, user_id: str, user_secret: str, account_uid: str):
        self.user_id = user_id
        self.user_secret = user_secret
        self.account_uid = account_uid
        self.client = httpx.AsyncClient(timeout=10.0)
        self._token_lock = asyncio.Lock()

    async def _get_token(self) -> str:
        async with self._token_lock:
            now = time.time()
            if self._token and now < self._token_expiry:
                return self._token

            url = "https://api.smartling.com/auth-api/v2/authenticate"
            payload = {"userIdentifier": self.user_id, "userSecret": self.user_secret}

            resp = await self.client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            self._token = data["response"]["data"]["accessToken"]
            # Refresh 1 minute before expiry (expiresIn is in seconds)
            expires_in = data["response"]["data"]["expiresIn"]
            self._token_expiry = now + expires_in - 60

            return self._token

    async def translate_batch(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling MT API for multiple languages.
        """
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        results = await asyncio.gather(
            *[self._translate_batch_single_lang(texts, lang) for lang in target_langs]
        )
        return dict(zip(target_langs, results, strict=True))

    async def _translate_batch_single_lang(self, texts: list[str], target_lang: str) -> list[str]:
        """
        Translates a batch of texts using Smartling MT API for a single target language.
        Retry on 401 once (token expiry race condition).
        Retry on 429 with randomized exponential backoff (1s to 30s).
        """
        backoff_seconds = 1.0
        max_backoff = 30.0
        max_attempts = 5
        last_error: httpx.HTTPStatusError | None = None

        for attempt in range(max_attempts):
            try:
                return await self._do_translate_batch(texts, target_lang)
            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                if status_code == 401:
                    # Force refresh
                    self._token = None
                    continue
                if status_code == 429 and attempt < max_attempts - 1:
                    sleep_for = random.uniform(0, backoff_seconds)
                    logging.warning(
                        "Smartling MT API rate limited (429) for lang %s. Backing off for %.2fs.",
                        target_lang,
                        sleep_for,
                    )
                    await asyncio.sleep(sleep_for)
                    backoff_seconds = min(max_backoff, backoff_seconds * 2)
                    continue
                raise e

        if last_error is not None:
            raise httpx.HTTPStatusError(
                f"Smartling MT API rate limit retry attempts exceeded for lang {target_lang}",
                request=last_error.request,
                response=last_error.response,
            )

        raise RuntimeError("Smartling MT API retry loop exited unexpectedly")

    async def _do_translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        token = await self._get_token()

        # MT Router API handles multiple items
        url = f"https://api.smartling.com/mt-router-api/v2/accounts/{self.account_uid}/smartling-mt"

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Use the string index as the key to ensure order mapping
        payload = {
            "sourceLocaleId": "en",
            "targetLocaleId": target_lang,
            "items": [{"key": str(i), "sourceText": text} for i, text in enumerate(texts)],
        }

        try:
            # The MT API can handle up to 1000 items, which is likely plenty for our alerts.
            # If we ever exceed this, we'd need to chunk the texts here.
            resp = await self.client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.error(
                "Smartling MT API error: %s - %s", e.response.status_code, e.response.text
            )
            raise e
        except Exception as e:
            logging.exception("Unexpected error calling Smartling MT API")
            raise e

        data = resp.json()
        # Response format:
        # { "response": { "data": { "items": [ { "key": "0", "translationText": "..." }, ... ] } } }
        items = data["response"]["data"]["items"]

        # Sort by key (index) to maintain original order
        sorted_items = sorted(items, key=lambda x: int(x["key"]))
        return [item["translationText"] for item in sorted_items]

    async def close(self) -> None:
        await self.client.aclose()


class SmartlingJobBatchesTranslator(SmartlingTranslator):
    def __init__(self, user_id: str, user_secret: str, project_id: str, source_uri: str):
        # We don't need account_uid for Job Batches V2
        super().__init__(user_id, user_secret, "")
        self.project_id = project_id
        self.source_uri = source_uri

    async def translate_batch(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling Job Batches V2 API.
        1. Get or create Job
        2. Create Batch
        3. Upload file to Batch
        4. Poll Batch for status
        5. Download translated files
        """
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Get or create Job
        job_url = f"https://api.smartling.com/job-batches-api/v2/projects/{self.project_id}/jobs"
        job_payload = {
            "nameTemplate": "GTFS Alerts Translation",
            "mode": "REUSE_EXISTING",
            "salt": "RANDOM_ALPHANUMERIC",
            "targetLocaleIds": target_langs,
        }
        resp = await self.client.post(job_url, headers=headers, json=job_payload)
        resp.raise_for_status()
        job_uid = resp.json()["response"]["data"]["translationJobUid"]

        # 2. Create Batch
        batch_url = (
            f"https://api.smartling.com/job-batches-api/v2/projects/{self.project_id}/batches"
        )
        batch_payload = {
            "authorize": True,
            "translationJobUid": job_uid,
            "fileUris": [self.source_uri],
        }
        resp = await self.client.post(batch_url, headers=headers, json=batch_payload)
        resp.raise_for_status()
        batch_uid = resp.json()["response"]["data"]["batchUid"]

        # 3. Upload file to Batch
        upload_url = f"https://api.smartling.com/job-batches-api/v2/projects/{self.project_id}/batches/{batch_uid}/file"
        file_content = json.dumps(texts).encode("utf-8")
        files = {
            "file": ("strings.json", file_content, "application/json"),
        }
        # Multi-part form data
        data = {
            "fileUri": self.source_uri,
            "fileType": "json",
        }
        # Multi-value field for localeIdsToAuthorize[]
        multi_data = [("localeIdsToAuthorize[]", lang) for lang in target_langs]

        # Use httpx.Request to build multipart correctly if needed, or just pass everything to post
        # httpx handles 'data' as form fields and 'files' as files.
        # We MUST pass multi_data as a list of tuples to handle multiple keys with same name.

        # WORKAROUND: For multipart in AsyncClient with string/bytes,
        # it seems we need to use 'content' for the body if we want it fully async,
        # OR just accept that it might be sync for multipart.
        # But wait, httpx IS supposed to handle this.
        # Let's try passing 'files' but putting all parameters in 'data' as strings.

        form_data = list(data.items()) + multi_data

        # If we have both data and files, httpx uses multipart/form-data.
        # Let's try to just use post without data= and use files for everything?
        # Smartling expects them as form fields.

        resp = await self.client.post(
            upload_url, headers=headers, files={**files, **{k: (None, v) for k, v in form_data}}
        )
        resp.raise_for_status()

        # 4. Poll Batch for status
        status_url = f"https://api.smartling.com/job-batches-api/v2/projects/{self.project_id}/batches/{batch_uid}"
        while True:
            resp = await self.client.get(status_url, headers=headers)
            resp.raise_for_status()
            batch_data = resp.json()["response"]["data"]
            status = batch_data.get("status")
            logging.info("Smartling Job Batch %s status: %s", batch_uid, status)
            if status == "COMPLETED":
                break
            if status == "FAILED":
                raise RuntimeError(f"Smartling Job Batch failed: {batch_data}")
            await asyncio.sleep(1)

        # 5. Download translated files
        async def download_lang(lang: str) -> list[str]:
            dl_url = (
                f"https://api.smartling.com/files-api/v2/projects/{self.project_id}/locales/"
                f"{lang}/file"
            )
            dl_params = {"fileUri": self.source_uri, "retrievalType": "published"}
            resp = await self.client.get(dl_url, headers=headers, params=dl_params)
            resp.raise_for_status()
            result = resp.json()
            if not isinstance(result, list):
                raise ValueError(
                    f"Expected JSON list response from Smartling Files API for {lang}, "
                    f"got {type(result)}"
                )
            return result

        results = await asyncio.gather(*[download_lang(lang) for lang in target_langs])
        return dict(zip(target_langs, results, strict=True))


class SmartlingFileTranslator(SmartlingTranslator):
    async def translate_batch(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling File Translation API.
        1. Upload file
        2. Start MT process
        3. Poll for status
        4. Download translated files (parallelized for target_langs)
        """
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload file
        upload_url = (
            f"https://api.smartling.com/file-translations-api/v2/accounts/{self.account_uid}/files"
        )
        file_content = json.dumps(texts).encode("utf-8")
        files = {
            "file": ("strings.json", file_content, "application/json"),
            "request": (None, json.dumps({"fileType": "json"}).encode("utf-8"), "application/json"),
        }

        resp = await self.client.post(upload_url, headers=headers, files=files)
        if resp.status_code == 400:
            logging.error("Smartling MT File API 400 Bad Request: %s", resp.text)
        resp.raise_for_status()
        file_uid = resp.json()["response"]["data"]["fileUid"]

        # 2. Start MT process
        mt_url = (
            f"https://api.smartling.com/file-translations-api/v2/accounts/"
            f"{self.account_uid}/files/{file_uid}/mt"
        )
        mt_payload = {"targetLocaleIds": target_langs, "sourceLocaleId": "en"}
        resp = await self.client.post(mt_url, headers=headers, json=mt_payload)
        resp.raise_for_status()
        mt_uid = resp.json()["response"]["data"]["mtUid"]

        # 3. Poll for status
        status_url = (
            f"https://api.smartling.com/file-translations-api/v2/accounts/"
            f"{self.account_uid}/files/{file_uid}/mt/{mt_uid}/status"
        )
        while True:
            resp = await self.client.get(status_url, headers=headers)
            resp.raise_for_status()
            status_data = resp.json()["response"]["data"]
            # File Translation API uses 'state', Job Batches uses 'status'
            status = status_data.get("status") or status_data.get("state")
            logging.info("Smartling MT File %s state: %s", mt_uid, status)
            if status == "COMPLETED":
                break
            if status == "FAILED":
                raise RuntimeError(f"Smartling MT File process failed: {status_data}")
            await asyncio.sleep(1)

        # 4. Download translated files
        async def download_lang(lang: str) -> list[str]:
            dl_url = (
                f"https://api.smartling.com/file-translations-api/v2/accounts/"
                f"{self.account_uid}/files/{file_uid}/mt/{mt_uid}/locales/{lang}/file"
            )
            resp = await self.client.get(dl_url, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            if not isinstance(result, list):
                raise ValueError(
                    f"Expected JSON list response from Smartling MT File API for {lang}, "
                    f"got {type(result)}"
                )
            return result

        results = await asyncio.gather(*[download_lang(lang) for lang in target_langs])
        return dict(zip(target_langs, results, strict=True))
