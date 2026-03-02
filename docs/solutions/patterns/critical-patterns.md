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
