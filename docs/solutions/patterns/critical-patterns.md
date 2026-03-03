# Critical Patterns for GTFS Alerts Translation Lambda

These patterns were extracted from real issues encountered during development. Review before making changes.

## Pattern 1: Language Code Mapping

**Common symptom:** Language codes in output don't match GTFS standards

❌ WRONG - Using Smartling codes directly:
```python
self.target_languages = "es-LA"  # Smartling code, not GTFS
```

✅ CORRECT - Use GTFS codes, map to Smartling:
```python
self.target_languages = "es-419"  # GTFS standard

# When calling Smartling API:
smartling_code = to_smartling_code("es-419")  # Returns "es-LA"

# When processing Smartling response:
gtfs_code = from_smartling_code("es-LA")  # Returns "es-419"
```

**Examples:**
- [language-code-mapping-smartling-20260220.md](./integration-issues/language-code-mapping-smartling-20260220.md)

---

## Pattern 2: Graceful Degradation for External Services

**Common symptom:** Lambda fails entirely when translation service is slow/unavailable

❌ WRONG - Let translation failure kill the Lambda:
```python
metrics = await FeedProcessor.process_feed(...)  # No timeout
# If this hangs, Lambda times out with no output
```

✅ CORRECT - Use timeout with fallback:
```python
try:
    metrics = await asyncio.wait_for(
        FeedProcessor.process_feed(...),
        timeout=settings.translation_timeout,
    )
except asyncio.TimeoutError:
    logger.warning("Translation timed out, publishing without translations")
    # Continue to publish untranslated feed
```

**Key principle:** Users should always get alerts, even if translations fail.

**Examples:**
- [translation-timeout-resilience-20260224.md](./runtime-errors/translation-timeout-resilience-20260224.md)

---

## Pattern 3: Normalize Strings Before Cache Lookup

**Common symptom:** Translation reuse lower than expected

❌ WRONG - Use raw strings as cache keys:
```python
translation_map[english_text] = translations  # May have whitespace
```

✅ CORRECT - Normalize before caching and lookup:
```python
normalized_key = english_text.strip()
translation_map[normalized_key] = translations

# When looking up:
lookup_key = source_text.strip()
translations = translation_map.get(lookup_key)
```

**Examples:**
- [whitespace-translation-reuse-20260223.md](./runtime-errors/whitespace-translation-reuse-20260223.md)

---

## Pattern 4: API Multi-Value Parameter Format

**Common symptom:** Only some values processed from multi-value API parameters

❌ WRONG - Multiple form fields with same name:
```python
for lang in target_langs:
    form_data.append(("localeIdsToAuthorize[]", lang))
```

✅ CORRECT - Single field with comma-separated values:
```python
form_data.append(("localeIdsToAuthorize[]", ",".join(target_langs)))
```

**Note:** Always verify exact format expected by APIs, especially for array/multi-value params.

**Examples:**
- [smartling-locale-authorization-20260223.md](./integration-issues/smartling-locale-authorization-20260223.md)

---

## Pattern 5: Debug Cache Misses with Key Comparison

**Common symptom:** Strings not being reused but unclear why

❌ WRONG - Assume logic is broken:
```python
# Just change the code without understanding the issue
```

✅ CORRECT - Log and compare keys:
```python
logging.debug("OLD keys: %s", list(old_map.keys())[:10])
logging.debug("NEW keys: %s", list(new_map.keys())[:10])

# Find mismatches
missing = set(new_map.keys()) - set(old_map.keys())
logging.debug("Keys in new but not old: %s", missing)
```

**Examples:**
- [service-effect-translation-reuse-20260223.md](./integration-issues/service-effect-translation-reuse-20260223.md)

---

## Pattern 6: AWS SDK Requires Region in CI

**Common symptom:** Tests pass locally but fail in GitHub Actions with botocore errors

❌ WRONG - Assume CI has AWS config:
```yaml
- name: Run tests
  run: mise run test
```

✅ CORRECT - Set AWS_DEFAULT_REGION:
```yaml
- name: Run tests
  env:
    AWS_DEFAULT_REGION: us-east-1
  run: mise run test
```

**Note:** Botocore requires a region even when endpoints are mocked.

**Examples:**
- [botocore-region-required-ci-20260203.md](../build-errors/botocore-region-required-ci-20260203.md)

---

## Pattern 7: Explicit Type Annotations for JSON

**Common symptom:** Mypy error "Collection[str] is not indexable"

❌ WRONG - Let mypy infer JSON types:
```python
result = processor.to_json(feed)
value = result["entity"][0]  # mypy: Collection is not indexable
```

✅ CORRECT - Add explicit type annotations:
```python
from typing import Any

result: dict[str, Any] = processor.to_json(feed)
value = result["entity"][0]  # Works
```

**Examples:**
- [mypy-collection-indexing-20260204.md](../build-errors/mypy-collection-indexing-20260204.md)

---

## Pattern 8: Extract Shared Logic to Core Modules

**Common symptom:** Circular imports when scripts import from lambda_handler

❌ WRONG - Put reusable logic in lambda_handler:
```python
# scripts/run_local.py
from gtfs_translation.lambda_handler import fetch_source  # Circular!
```

✅ CORRECT - Extract to core module:
```python
# gtfs_translation/core/fetcher.py
async def fetch_source(url: str) -> tuple[bytes, str]: ...

# scripts/run_local.py
from gtfs_translation.core.fetcher import fetch_source  # Clean
```

**Examples:**
- [fetcher-module-extraction-20260203.md](../developer-experience/fetcher-module-extraction-20260203.md)
