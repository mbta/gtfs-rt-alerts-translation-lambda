---
title: Add Stop Name Placeholder Substitution
type: feat
date: 2026-02-12
---

# Add Stop Name Placeholder Substitution

## Overview

Implement placeholder substitution for MBTA stop names to avoid unnecessary translation costs and prevent mistranslation of proper nouns. The Lambda will fetch stop names from the MBTA API at startup, replace them with Smartling-compatible placeholders (`{0}`, `{1}`, etc.) before translation, and restore the original names after translation.

**⚠️ CRITICAL DESIGN CONSTRAINT:** Placeholder substitution must be applied to **BOTH** the new feed AND the old feed before the translation diffing logic runs. Otherwise, the diffing won't match (e.g., `"Service at {0}"` vs `"Service at Park Street"`), breaking translation reuse and significantly increasing costs.

## Problem Statement / Motivation

Currently, the Lambda sends all English text from GTFS alerts to Smartling for translation, including proper nouns like stop names ("Park Street", "South Station", etc.). This:

1. **Increases translation costs** - Stop names are repeated frequently across alerts
2. **Risks mistranslation** - Translation services may attempt to translate proper nouns (e.g., "Park Street" → "Calle del Parque")
3. **Creates inconsistency** - The same stop name might be translated differently across alerts

Smartling supports placeholders using `{x}` syntax, which are preserved during translation. By substituting stop names with placeholders, we eliminate these issues.

## Proposed Solution

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Lambda Startup                                                   │
├─────────────────────────────────────────────────────────────────┤
│ 1. Fetch stop names from MBTA API                               │
│    GET https://api-v3.mbta.com/stops?filter[location_type]=1    │
│                                      &fields[stop]=name          │
│ 2. Build stop name index (trie or sorted list)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ For Each Alert (FeedProcessor.process_feed)                     │
├─────────────────────────────────────────────────────────────────┤
│ 3a. Pre-process NEW feed English text:                          │
│     "Service at Park Street" → "Service at {0}"                 │
│     Store mapping: {0 → "Park Street"}                          │
│                                                                  │
│ 3b. Pre-process OLD feed English text (CRITICAL FOR REUSE):     │
│     OLD: "Service at Park Street" → "Service at {0}"            │
│     This ensures diffing matches: NEW{0} == OLD{0}              │
│                                                                  │
│ 3c. Pre-process OLD feed translations:                          │
│     OLD ES: "Servicio en Park Street" → "Servicio en {0}"       │
│     (Apply same substitution to existing translations)          │
├─────────────────────────────────────────────────────────────────┤
│ 4. Diff logic (UNCHANGED):                                      │
│    NEW: "Service at {0}" matches OLD: "Service at {0}"          │
│    → Reuse OLD ES: "Servicio en {0}" ✅                          │
├─────────────────────────────────────────────────────────────────┤
│ 5. Send only NEW strings to Smartling:                          │
│    EN: "Delays at {1}" (not in old feed)                        │
│    ES: "Retrasos en {1}"                                         │
├─────────────────────────────────────────────────────────────────┤
│ 6. Post-process ALL translations (reused + new):                │
│    "Servicio en {0}" → "Servicio en Park Street"                │
│    "Retrasos en {1}" → "Retrasos en South Station"              │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight:** Placeholder substitution must be applied to BOTH the new feed AND the old feed's English + translation text. This ensures the translation diffing logic can correctly match strings and reuse existing translations.

### Implementation Phases

#### Phase 1: Stop Name Fetcher (New Module)

Create `gtfs_translation/core/stop_fetcher.py`:

**Key responsibilities:**
- Fetch stop names from MBTA API with error handling and retries
- Parse JSON response and extract stop names
- Build efficient lookup structure (trie for longest-match or sorted list)
- Cache stop names for Lambda container reuse

**API Details:**
- Endpoint: `https://api-v3.mbta.com/stops?filter[location_type]=1&fields[stop]=name`
- Response format: `{"data": [{"id": "place-pktrm", "attributes": {"name": "Park Street"}}, ...]}`
- Filter `location_type=1` returns only stations (not platforms)
- `fields[stop]=name` reduces payload size

**Example response:**
```json
{
  "data": [
    {"id": "place-alfcl", "attributes": {"name": "Alewife"}},
    {"id": "place-pktrm", "attributes": {"name": "Park Street"}},
    {"id": "place-sstat", "attributes": {"name": "South Station"}}
  ]
}
```

**Success criteria:**
- [ ] Fetches stops with exponential backoff (3 retries)
- [ ] Raises clear exception if API is unreachable
- [ ] Returns list of stop names sorted by length (longest first)
- [ ] Logs count of stops fetched at NOTICE level

#### Phase 2: Placeholder Substitution (New Module)

Create `gtfs_translation/core/placeholder.py`:

**Key responsibilities:**
- Replace stop names with `{0}`, `{1}`, `{2}`, etc. (greedy longest-match)
- Store bidirectional mapping: `{placeholder → original_name}`
- Restore placeholders after translation
- Handle edge cases (overlapping names, case sensitivity, punctuation)

**Algorithm (Greedy Longest-Match):**
```python
# Example with stops: ["Park Street", "Park", "Street"]
# Input: "Service at Park Street and Park"
# 1. Find longest match: "Park Street" (not "Park" alone)
# 2. Replace: "Service at {0} and Park"
# 3. Find next match: "Park"
# 4. Replace: "Service at {0} and {1}"
# Mapping: {0: "Park Street", 1: "Park"}
```

**Edge cases:**
- **Case sensitivity**: "park street" vs "Park Street" → normalize to title case
- **Punctuation boundaries**: "at Park Street." → "at {0}."
- **Overlapping names**: "Park" and "Park Street" → prefer longer match
- **Already-present placeholders**: Don't double-substitute text that already has `{x}`

**Success criteria:**
- [ ] Substitutes stop names with numbered placeholders
- [ ] Returns mapping dict for restoration
- [ ] Handles case-insensitive matching
- [ ] Preserves punctuation and whitespace
- [ ] Restores placeholders correctly in translations

#### Phase 3: Integration with FeedProcessor

Modify `gtfs_translation/core/processor.py`:

**Changes to `FeedProcessor.process_feed()`:**
1. Accept optional `stop_names: list[str]` parameter
2. **BEFORE** collecting translations from old feed, apply placeholder substitution to old feed
3. **BEFORE** collecting English strings from new feed, apply placeholder substitution to new feed
4. **AFTER** translation, restore stop names from placeholders

**Critical: Old Feed Substitution for Translation Reuse**

The translation diffing logic works by comparing English text from the new feed with English text from the old feed. If they match, it reuses the old translations. **We must apply placeholder substitution to the old feed as well**, otherwise:

```python
# WITHOUT old feed substitution (BROKEN):
NEW English: "Service at {0}"  # Substituted
OLD English: "Service at Park Street"  # NOT substituted
→ No match, can't reuse translation ❌

# WITH old feed substitution (CORRECT):
NEW English: "Service at {0}"  # Substituted
OLD English: "Service at {0}"  # Also substituted
→ Match! Reuse OLD translation ✅
```

**New helper methods:**
```python
@classmethod
def _substitute_placeholders_in_feed(
    cls,
    feed: gtfs_realtime_pb2.FeedMessage,
    json_data: dict[str, Any] | None,
    stop_names: list[str]
) -> None:
    """
    Apply placeholder substitution IN-PLACE to all text fields in a feed.
    Modifies both Protobuf and JSON representations.
    Must be called on BOTH new feed and old feed before diffing.
    """
    pass

@classmethod
def _substitute_placeholders(
    cls,
    text: str,
    stop_names: list[str]
) -> tuple[str, dict[str, str]]:
    """Replace stop names with {0}, {1}, etc. Returns (substituted_text, mapping)."""
    pass

@classmethod
def _restore_placeholders_in_feed(
    cls,
    feed: gtfs_realtime_pb2.FeedMessage,
    json_data: dict[str, Any] | None,
) -> None:
    """
    Restore stop names from placeholders IN-PLACE after translation.
    The mapping is stored in the placeholder itself (deterministic).
    """
    pass
```

**Processing flow:**
```python
async def process_feed(
    cls,
    feed: gtfs_realtime_pb2.FeedMessage,
    old_feed: gtfs_realtime_pb2.FeedMessage | None,
    translator: "Translator",
    target_langs: list[str],
    stop_names: list[str] | None = None,
    ...
) -> ProcessingMetrics:
    # STEP 1: Apply placeholder substitution to BOTH feeds
    if stop_names:
        cls._substitute_placeholders_in_feed(feed, source_json, stop_names)
        if old_feed:
            cls._substitute_placeholders_in_feed(old_feed, dest_json, stop_names)
    
    # STEP 2: Collect translations from old feed (now with placeholders)
    old_translation_map = cls._gather_translations_from_feed(
        old_feed, dest_json, include_all_translations=True
    )
    # OLD: {"Service at {0}": {"es": "Servicio en {0}"}}
    
    # STEP 3: Collect English strings from new feed (now with placeholders)
    new_english_map = cls._gather_translations_from_feed(
        feed, source_json, include_all_translations=False
    )
    # NEW: {"Service at {0}": {}}
    
    # STEP 4: Diff logic (UNCHANGED - but now comparing placeholder text)
    # NEW "Service at {0}" matches OLD "Service at {0}"
    # → Reuse OLD translation "Servicio en {0}"
    
    # STEP 5: Translate missing strings (with placeholders)
    # Only strings not in old_translation_map get sent to Smartling
    
    # STEP 6: Apply translations to feed (still has placeholders)
    
    # STEP 7: Restore stop names in ALL translations (reused + new)
    if stop_names:
        cls._restore_placeholders_in_feed(feed, source_json)
    
    return metrics
```

**Deterministic Placeholder Mapping:**

To restore placeholders without storing mappings, we use **deterministic placeholder assignment** based on stop name order:

```python
# Global ordered list (same for all alerts)
stop_names = ["South Station", "Park Street", "Park"]  # Sorted longest-first

# Any text with "South Station" always gets {0}
# Any text with "Park Street" always gets {1}  
# Any text with "Park" always gets {2}

# This allows restoration without per-alert mapping storage
```

**Success criteria:**
- [ ] Substitutes placeholders in both new AND old feeds
- [ ] Preserves translation diffing logic (matches on placeholder text)
- [ ] Restores placeholders after translation
- [ ] Works with all text fields (header_text, description_text, enhanced JSON)
- [ ] Uses deterministic placeholder assignment for easy restoration

#### Phase 4: Lambda Handler Integration

Modify `gtfs_translation/lambda_handler.py`:

**Changes to `run_translation()`:**
1. Fetch stop names at start of function (cache in Lambda container)
2. Pass stop names to `FeedProcessor.process_feed()`

**Caching strategy:**
```python
# Module-level cache for Lambda container reuse
_stop_names_cache: list[str] | None = None

async def run_translation(source_url: str, dest_urls: list[str]) -> None:
    global _stop_names_cache
    
    # Fetch stops once per container lifetime
    if _stop_names_cache is None:
        _stop_names_cache = await fetch_stop_names()
        logger.log(NOTICE_LEVEL, "Fetched %d stop names", len(_stop_names_cache))
    
    # ... existing logic ...
    
    metrics = await FeedProcessor.process_feed(
        new_feed,
        old_feed,
        translator,
        settings.target_lang_list,
        concurrency_limit=settings.concurrency_limit,
        source_json=source_json,
        dest_json=dest_json,
        stop_names=_stop_names_cache,  # NEW PARAMETER
    )
```

**Success criteria:**
- [ ] Fetches stops on first invocation
- [ ] Reuses stops across invocations in same container
- [ ] Logs stop count at startup
- [ ] Degrades gracefully if MBTA API is unavailable

## Technical Considerations

### Performance
- **Trie vs Sorted List**: For ~200 stops, sorted list (O(n) per substitution) is simpler than trie (O(m) where m=text length). Longest-first sorting enables greedy matching.
- **Lambda Cold Start**: Adding 1-2s for API call on cold start is acceptable (happens once per container)
- **Container Reuse**: Stop names cached at module level, no refetch on warm invocations

### Error Handling
- **MBTA API Failure**: Log warning and proceed without placeholders (graceful degradation)
- **Invalid Placeholder Format**: If Smartling returns malformed placeholders, log error and use original translation
- **Partial Matches**: If only some placeholders are restored, log warning with details

### Testing Strategy
- **Unit tests**: Placeholder substitution/restoration logic in isolation
- **Integration tests**: End-to-end with mock MBTA API and mock translator
- **Edge case tests**: Overlapping names, punctuation, case sensitivity
- **Regression tests**: Ensure existing translation diffing still works
- **Old feed reuse test**: CRITICAL - Verify that substituting placeholders in old feed preserves translation reuse
  ```python
  # Test case: Old feed has "Service at Park Street" with translation
  # New feed has same text
  # After substitution, both should have "Service at {0}"
  # Verify translation is reused (not sent to Smartling)
  ```

### Security
- **API Endpoint**: MBTA API is public, no authentication required
- **Input Validation**: Sanitize stop names (no special regex characters)
- **Placeholder Injection**: Validate that restored text doesn't contain new placeholders

## Acceptance Criteria

### Functional Requirements
- [ ] Fetches stop names from MBTA API at Lambda startup
- [ ] Replaces stop names with `{0}`, `{1}`, etc. before translation in BOTH new and old feeds
- [ ] Sends placeholder text to Smartling
- [ ] Restores stop names in translated text
- [ ] Handles all text fields (header_text, description_text, enhanced JSON fields)
- [ ] Caches stop names across Lambda invocations
- [ ] **CRITICAL**: Preserves translation reuse by applying placeholders to old feed before diffing

### Non-Functional Requirements
- [ ] Adds <2s to cold start time
- [ ] Zero impact on warm invocations (cache hit)
- [ ] No breaking changes to existing behavior
- [ ] Graceful degradation if MBTA API is unavailable
- [ ] Translation reuse rate remains unchanged (or improves)

### Quality Gates
- [ ] 90%+ test coverage on new modules
- [ ] All existing tests pass
- [ ] `mise run format` passes
- [ ] `mise run check` passes (mypy)
- [ ] Integration test with real MBTA API endpoint
- [ ] Test verifying old feed placeholder substitution preserves reuse

## Success Metrics

1. **Cost Reduction**: Measure characters sent to Smartling before/after (expect 10-20% reduction)
2. **Translation Quality**: Verify stop names are not translated (manual spot-check)
3. **Performance**: Cold start <3s, warm invocation <500ms (unchanged)
4. **Translation Reuse**: Monitor `translations_reused` metric - should NOT decrease after deployment
4. **Reliability**: Zero failures due to placeholder logic (monitor CloudWatch logs)

## Dependencies & Risks

### Dependencies
- MBTA API availability (public endpoint, no SLA)
- Smartling placeholder format (`{x}` notation)
- Existing translation diffing logic (must preserve)

### Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MBTA API downtime | Medium | Low | Cache stops, degrade gracefully |
| Stop names change | Low | Low | Re-fetch on each cold start |
| Placeholder format mismatch | Low | High | Validate Smartling docs, add integration test |
| **Breaking translation reuse** | Medium | Critical | **Apply placeholders to old feed BEFORE diffing** |
| Regression in translation diffing | Low | High | Comprehensive regression tests |

## Implementation Plan

### File Changes

#### New Files
1. `gtfs_translation/core/stop_fetcher.py` - MBTA API client
   ```python
   async def fetch_stop_names() -> list[str]:
       """Fetch stop names from MBTA API, sorted by length (longest first)."""
       pass
   ```

2. `gtfs_translation/core/placeholder.py` - Substitution logic
   ```python
   def substitute_stop_names(text: str, stop_names: list[str]) -> tuple[str, dict[str, str]]:
       """Replace stop names with {0}, {1}, etc. Returns (text, mapping)."""
       pass
   
   def restore_stop_names(text: str, mapping: dict[str, str]) -> str:
       """Restore stop names from placeholders using mapping."""
       pass
   ```

3. `tests/unit/test_stop_fetcher.py` - Stop fetcher tests
   - Test successful fetch
   - Test retry logic
   - Test error handling

4. `tests/unit/test_placeholder.py` - Placeholder logic tests
   - Test basic substitution
   - Test overlapping names
   - Test case sensitivity
   - Test restoration

5. `tests/integration/test_placeholder_e2e.py` - End-to-end test
   - Test with real MBTA API
   - Test with mock translator
   - Verify stop names are preserved

#### Modified Files
1. `gtfs_translation/core/processor.py`
   - Add `stop_names: list[str] | None = None` parameter to `process_feed()`
   - Add `_substitute_placeholders_in_feed()` helper method (applies to entire feed)
   - Add `_substitute_placeholders()` helper method (applies to single text)
   - Add `_restore_placeholders_in_feed()` helper method
   - **Call substitution on BOTH new and old feeds BEFORE diffing**
   - Call restoration after translation

2. `gtfs_translation/lambda_handler.py`
   - Add module-level cache: `_stop_names_cache: list[str] | None = None`
   - Fetch stops in `run_translation()` if cache is empty
   - Pass `stop_names` to `FeedProcessor.process_feed()`

3. `tests/unit/test_processor.py`
   - Add test for placeholder substitution in new feed
   - **Add test for placeholder substitution in old feed (CRITICAL)**
   - Add test verifying translation reuse with placeholders
   - Add test for placeholder restoration
   - Add test for error handling when stop names are None

### Implementation Order
1. **Phase 1**: Stop fetcher (`stop_fetcher.py` + tests) ✅ Self-contained
2. **Phase 2**: Placeholder logic (`placeholder.py` + tests) ✅ Self-contained
3. **Phase 3**: Processor integration (modify `processor.py` + tests) ⚠️ Requires Phase 1 & 2
4. **Phase 4**: Lambda handler integration (modify `lambda_handler.py` + tests) ⚠️ Requires Phase 3

## Testing Checklist

### Unit Tests
- [ ] `test_stop_fetcher.py`: Fetch, retry, error handling
- [ ] `test_placeholder.py`: Substitution edge cases
- [ ] `test_placeholder.py`: Restoration edge cases
- [ ] `test_processor.py`: Integration with FeedProcessor
- [ ] **`test_processor.py`: CRITICAL - Verify old feed substitution preserves translation reuse**
  ```python
  # Test: old feed with "Service at Park Street" translated to "Servicio en Park Street"
  # New feed with same English text
  # After substitution: both have "Service at {0}" and "Servicio en {0}"
  # Assert: translation is reused (MockTranslator.translate_batch NOT called)
  # Assert: metrics.translations_reused == 1
  ```

### Integration Tests
- [ ] `test_placeholder_e2e.py`: Real MBTA API + mock translator
- [ ] Verify stop names preserved across all text fields
- [ ] Verify translation diffing still works with placeholders
- [ ] Test scenario: deploy with placeholders, old feeds without placeholders (migration test)

### Manual Testing
- [ ] Deploy to dev environment
- [ ] Trigger Lambda with real MBTA feed
- [ ] Verify stop names in translated output (Spanish, French, Portuguese)
- [ ] Check CloudWatch logs for stop count and metrics

## Documentation Plan

- [ ] Update README.md with placeholder feature description
- [ ] Add architecture diagram showing placeholder flow
- [ ] Document MBTA API endpoint in AGENTS.md
- [ ] Add troubleshooting section for MBTA API failures

## References & Research

### Internal References
- Processor logic: `gtfs_translation/core/processor.py:80-120` (translation collection)
- Translator interface: `gtfs_translation/core/translator.py:5-15` (translate_batch)
- Lambda handler: `gtfs_translation/lambda_handler.py:45-80` (run_translation)
- Configuration: `gtfs_translation/config.py` (environment variables)

### External References
- MBTA API: `https://api-v3.mbta.com/stops?filter[location_type]=1&fields[stop]=name`
- MBTA API Docs: `https://www.mbta.com/developers/v3-api`
- Smartling Placeholder Docs: `https://help.smartling.com/hc/en-us/articles/360008000733-Placeholders`
- GTFS-Realtime Spec: `https://gtfs.org/realtime/reference/`

### Related Work
- Original brainstorm: `docs/brainstorms/2026-02-03-gtfs-alerts-translation-lambda-brainstorm.md`
- Language mapping feature: `gtfs_translation/config.py:3-18` (es-419 ↔ es-LA)

## Future Considerations

1. **Configurable Stop Sources**: Support other transit agencies (e.g., NYC MTA, SF MUNI)
2. **Route Names**: Apply same logic to route names ("Red Line", "Bus 39")
3. **Placeholder Caching**: Store placeholder mappings in S3 for cross-container reuse
4. **Analytics**: Track substitution rate (% of text that is stop names)
5. **Dynamic Reloading**: Periodically refresh stop names (e.g., every 24 hours)
