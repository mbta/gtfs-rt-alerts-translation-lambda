import asyncio
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
        self.client = httpx.Client(timeout=10.0)

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token

        url = "https://api.smartling.com/auth-api/v2/authenticate"
        payload = {"userIdentifier": self.user_id, "userSecret": self.user_secret}

        resp = self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        self._token = data["response"]["data"]["accessToken"]
        # Refresh 1 minute before expiry (expiresIn is in seconds)
        expires_in = data["response"]["data"]["expiresIn"]
        self._token_expiry = now + expires_in - 60

        return self._token

    def translate_batch(self, texts: list[str], target_langs: list[str]) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling MT API for multiple languages.
        """
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        logging.info(
            "Smartling translate_batch request: target_langs=%s, count=%d, texts=%s",
            target_langs,
            len(texts),
            texts,
        )

        results = []
        for lang in target_langs:
            results.append(self._translate_batch_single_lang(texts, lang))

        return dict(zip(target_langs, results, strict=True))

    def _translate_batch_single_lang(self, texts: list[str], target_lang: str) -> list[str]:
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
                return self._do_translate_batch(texts, target_lang)
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
                    time.sleep(sleep_for)
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

    def _do_translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        token = self._get_token()

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
            resp = self.client.post(url, headers=headers, json=payload)
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

    def close(self) -> None:
        """
        Closes the underlying HTTP client.
        """
        self.client.close()


class SmartlingFileTranslator(SmartlingTranslator):
    def translate_batch(self, texts: list[str], target_langs: list[str]) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling File Translation API.
        1. Upload file
        2. Start MT process
        3. Poll for status
        4. Download translated files
        """
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload file
        upload_url = (
            f"https://api.smartling.com/file-translations-api/v2/accounts/{self.account_uid}/files"
        )
        import json

        file_content = json.dumps(texts)
        files = {"file": ("strings.json", file_content, "application/json")}

        resp = self.client.post(upload_url, headers=headers, files=files)
        resp.raise_for_status()
        file_uid = resp.json()["response"]["data"]["fileUid"]

        # 2. Start MT process
        mt_url = f"https://api.smartling.com/file-translations-api/v2/accounts/{self.account_uid}/files/{file_uid}/mt"
        mt_payload = {"targetLocaleIds": target_langs, "sourceLocaleId": "en"}
        resp = self.client.post(mt_url, headers=headers, json=mt_payload)
        resp.raise_for_status()
        mt_uid = resp.json()["response"]["data"]["mtUid"]

        # 3. Poll for status
        status_url = f"https://api.smartling.com/file-translations-api/v2/accounts/{self.account_uid}/files/{file_uid}/mt/{mt_uid}/status"
        while True:
            resp = self.client.get(status_url, headers=headers)
            resp.raise_for_status()
            status_data = resp.json()["response"]["data"]
            if status_data["status"] == "COMPLETED":
                break
            if status_data["status"] == "FAILED":
                raise RuntimeError(f"Smartling MT File process failed: {status_data}")
            time.sleep(1)

        # 4. Download translated files
        def download_lang(lang: str) -> list[str]:
            dl_url = f"https://api.smartling.com/file-translations-api/v2/accounts/{self.account_uid}/files/{file_uid}/mt/{mt_uid}/locales/{lang}/file"
            resp = self.client.get(dl_url, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            if not isinstance(result, list):
                raise ValueError(
                    f"Expected JSON list response from Smartling MT File API for {lang}, got {type(result)}"
                )
            return result

        results = [download_lang(lang) for lang in target_langs]
        return dict(zip(target_langs, results, strict=True))
