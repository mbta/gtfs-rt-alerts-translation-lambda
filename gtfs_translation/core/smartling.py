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

    def translate_batch(self, texts: list[str], target_langs: list[str]) -> dict[str, list[str]]:
        """
        Translates a batch of texts using Smartling MT API for multiple languages.
        Runs asynchronously internally.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._translate_batch_async(texts, target_langs))

        # If we are already in an event loop (e.g. called from another async function),
        # we can't use asyncio.run.
        # But the prompt says "The final API can appear to be synchronous".
        # In a Lambda or typical script, we might not be in a loop yet, or we might be.
        # If we are in a loop, we should probably run the coroutine and wait for it.
        # However, calling a sync function that blocks on an async task inside a loop
        # is generally a bad idea (it blocks the loop).
        # But for this specific task, if we want it to APPEAR synchronous:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(self._translate_batch_async(texts, target_langs))
            )
            return future.result()

    async def _translate_batch_async(
        self, texts: list[str], target_langs: list[str]
    ) -> dict[str, list[str]]:
        if not texts or not target_langs:
            return {lang: [] for lang in target_langs}

        logging.info(
            "Smartling translate_batch request: target_langs=%s, count=%d, texts=%s",
            target_langs,
            len(texts),
            texts,
        )

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
                    # We don't recurse here to avoid infinite loops if 401 persists
                    # Just let the loop continue and it will retry _do_translate_batch
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

class SmartlingFileTranslator(SmartlingTranslator):
    async def _do_translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """
        Translates a batch of texts using Smartling MT File API.
        """
        token = await self._get_token()

        url = f"https://api.smartling.com/mt-router-api/v2/accounts/{self.account_uid}/smartling-mt/file"

        headers = {"Authorization": f"Bearer {token}"}

        # Format strings as a JSON list for the "file" part
        import json

        file_content = json.dumps(texts)

        files = {
            "file": ("strings.json", file_content, "application/json"),
        }
        data = {
            "sourceLocaleId": "en",
            "targetLocaleId": target_lang,
            "fileType": "json",
        }

        try:
            # We must use a separate client or careful configuration because 
            # httpx.AsyncClient.post with 'files' and 'data' sends multipart/form-data.
            resp = await self.client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.error(
                "Smartling MT File API error: %s - %s", e.response.status_code, e.response.text
            )
            raise e
        except Exception as e:
            logging.exception("Unexpected error calling Smartling MT File API")
            raise e

        # The response for the file API is the translated JSON content directly
        result = resp.json()
        if not isinstance(result, list):
            raise ValueError(f"Expected JSON list response from Smartling MT File API, got {type(result)}")
        return result
