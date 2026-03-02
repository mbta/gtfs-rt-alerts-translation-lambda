---
module: Feed Processor
date: 2026-02-23
problem_type: runtime_error
component: service_object
symptoms:
  - "Translations not being reused for strings with leading/trailing whitespace"
  - "Duplicate translation requests for same content"
  - "Higher than expected Smartling API usage"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [translation, whitespace, reuse, normalization, processor]
---

# Troubleshooting: Whitespace Causing Translation Cache Misses

## Problem
Strings with leading or trailing whitespace were not matching cached translations, causing unnecessary translation requests even when the content was the same.

## Environment
- Module: Feed Processor
- Affected Component: `gtfs_translation/core/processor.py`
- Date: 2026-02-23

## Symptoms
- Translation reuse metrics lower than expected
- Same text being translated multiple times
- Whitespace-only differences causing cache misses

## What Didn't Work

**Direct solution:** The problem was identified and fixed using TDD on the first attempt.

## Solution

Strip leading/trailing whitespace from English text during both extraction and lookup phases.

**Code changes:**

```python
# In _extract_translations_from_json:
# Strip whitespace for consistent translation lookup
english_text = english_text.strip()

# In _apply_translations_json:
# Strip whitespace to match the translation map keys
english_text_stripped = english_text.strip()
translated_text = translation_map[english_text_stripped].get(lang)
```

**Tests added:**
```python
def test_strip_whitespace_from_translations():
    """Test that whitespace is stripped from source text."""
    # Text with whitespace
    text_with_ws = "  Hello World  "
    # Should match translation for "Hello World"

def test_strip_whitespace_reuse_translations():
    """Test that translations are reused for strings with whitespace."""
    # Old translation for "Test"
    # New source with "  Test  "
    # Should reuse, not re-translate
```

## Why This Works

By normalizing whitespace at extraction time, the translation cache keys are consistent regardless of whitespace variations in the source data. This ensures translations are properly reused.

## Prevention

- Always normalize strings (trim whitespace) before using as cache/lookup keys
- Add tests that verify whitespace handling explicitly
- Consider other normalization (unicode normalization) if needed

## Related Issues

No related issues documented yet.
