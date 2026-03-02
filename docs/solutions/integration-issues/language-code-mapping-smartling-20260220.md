---
module: Smartling Translator
date: 2026-02-20
problem_type: integration_issue
component: tooling
symptoms:
  - "es-LA is not a real GTFS language code"
  - "Language codes in output feeds do not match GTFS standards"
  - "Smartling API requires specific locale codes different from GTFS"
root_cause: config_error
resolution_type: code_fix
severity: high
tags: [smartling, language-codes, gtfs, es-419, es-la, configuration]
---

# Troubleshooting: Language Code Mapping Between GTFS and Smartling

## Problem
The system was using `es-LA` as a language code, which is a Smartling-specific code but not a valid GTFS standard code. GTFS feeds should use `es-419` (Latin American Spanish) for compliance.

## Environment
- Module: Smartling Translator / Config
- Affected Component: `gtfs_translation/config.py`, `gtfs_translation/core/smartling.py`
- Date: 2026-02-20

## Symptoms
- Feeds published with `es-LA` language codes instead of GTFS-standard `es-419`
- Inconsistency between configured languages and output feed languages

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt.

## Solution

Added a language code mapping system that:
1. Uses GTFS-standard codes (`es-419`) in configuration and output feeds
2. Maps to Smartling API codes (`es-LA`) when making translation requests
3. Maps back from Smartling codes to GTFS codes when processing responses

**Code changes:**

```python
# gtfs_translation/config.py

# Mapping from GTFS standard codes to Smartling API codes
SMARTLING_LANGUAGE_MAP: dict[str, str] = {
    "es-419": "es-LA",  # Latin American Spanish
}

# Reverse mapping for normalizing responses
GTFS_LANGUAGE_MAP: dict[str, str] = {v: k for k, v in SMARTLING_LANGUAGE_MAP.items()}


def to_smartling_code(gtfs_code: str) -> str:
    """Convert a GTFS language code to Smartling's code."""
    return SMARTLING_LANGUAGE_MAP.get(gtfs_code, gtfs_code)


def from_smartling_code(smartling_code: str) -> str:
    """Convert a Smartling language code back to GTFS code."""
    return GTFS_LANGUAGE_MAP.get(smartling_code, smartling_code)
```

Default language changed from `es-LA` to `es-419`:
```python
self.target_languages = os.environ.get("TARGET_LANGUAGES", "es-419")
```

All Smartling translator classes updated to use mapping functions.

## Why This Works

1. **GTFS Compliance**: The output feeds now contain valid GTFS language codes
2. **Smartling Compatibility**: The API calls use Smartling's expected codes
3. **Transparent Mapping**: The mapping happens automatically, so consumers don't need to worry about code differences

## Prevention

- Always use GTFS-standard language codes in configuration
- Document language code mappings in README
- Use the mapping functions (`to_smartling_code`, `from_smartling_code`) when interfacing with external translation services

## Related Issues

No related issues documented yet.
