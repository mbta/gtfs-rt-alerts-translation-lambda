---
module: Feed Processor
date: 2026-02-23
problem_type: integration_issue
component: service_object
symptoms:
  - "service_effect_text not being detected as re-used"
  - "Enhanced JSON fields not contributing to translation cache"
  - "Debugging why specific strings bypass cache"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [translation, enhanced-json, service-effect, debugging, cache]
---

# Troubleshooting: Enhanced JSON Fields Not Contributing to Translation Reuse

## Problem
Strings in enhanced JSON fields (like `service_effect_text`) were not being detected as re-used, causing unnecessary translation requests.

## Environment
- Module: Feed Processor
- Affected Component: `gtfs_translation/core/processor.py`
- Date: 2026-02-23

## Symptoms
- Log shows "Translating N new strings" including strings that should be cached
- `service_effect_text` translations being re-requested
- Translation reuse metrics lower than expected

## What Didn't Work

**Attempted Solution 1:** Assumed the logic was broken
- **Why it failed:** Initial testing showed the logic was actually correct

## Solution

The issue was actually related to **whitespace normalization** (see related issue). The debugging process revealed that:

1. The extraction logic for enhanced JSON fields was correct
2. Both PB and JSON sources contribute to the translation cache
3. The real issue was whitespace in source strings

**Debugging approach used:**
```python
# Added diagnostic logging
logging.debug(
    "OLD translations collected: %s",
    list(old_translation_map.keys())[:10]
)
logging.debug(
    "NEW English texts collected: %s", 
    list(new_english_map.keys())[:10]
)
```

This logging helped identify that keys were slightly different due to whitespace.

## Why This Works

Enhanced JSON field extraction was already implemented correctly in `_gather_translations_from_feed`. The method properly iterates through:
- PB fields: `header_text`, `description_text`
- JSON enhanced fields: `service_effect_text`, `timeframe_text`

The fix was actually in whitespace normalization, which made the keys match properly.

## Prevention

- Add comprehensive debug logging for cache operations
- Log both sides of comparisons (old keys vs new keys)
- Use set operations to identify mismatches: `new_keys - old_keys`
- Test with real-world data that includes whitespace variations

## Related Issues

- See also: [whitespace-translation-reuse-20260223.md](../runtime-errors/whitespace-translation-reuse-20260223.md)
