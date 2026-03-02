---
module: Smartling Translator
date: 2026-02-23
problem_type: integration_issue
component: tooling
symptoms:
  - "Smartling batch file upload failing"
  - "localeIdsToAuthorize[] parameter not accepted correctly"
  - "Multiple languages not being authorized in batch"
root_cause: wrong_api
resolution_type: code_fix
severity: high
tags: [smartling, api, multipart-form, batch-upload, locale-authorization]
---

# Troubleshooting: Smartling localeIdsToAuthorize[] Form Field Format

## Problem
When uploading files to Smartling's batch API, the `localeIdsToAuthorize[]` field was being formatted incorrectly, causing language authorizations to fail.

## Environment
- Module: Smartling Translator
- Affected Component: `gtfs_translation/core/smartling.py`
- Date: 2026-02-23

## Symptoms
- Batch file uploads not authorizing all target languages
- Translations only processing for some languages
- Inconsistent behavior with multiple target languages

## What Didn't Work

**Attempted Solution 1:** Using multiple form fields with the same name
- **Why it failed:** Smartling API expects comma-separated values in a single field

## Solution

Changed the form data construction from multiple fields to a single field with comma-separated locale IDs:

**Code changes:**

```python
# Before (broken):
for lang in target_langs:
    form_data.append(("localeIdsToAuthorize[]", lang))

# After (fixed):
form_data.append(("localeIdsToAuthorize[]", ",".join(target_langs)))
```

**Test added:**
```python
def test_upload_file_locale_ids_single_field():
    """Verify localeIdsToAuthorize[] is sent as single comma-separated field."""
    # Test that multiple languages result in ONE form field
    # with value "es,fr,pt" not three separate fields
```

## Why This Works

Smartling's Batches API expects the `localeIdsToAuthorize[]` form field to contain all locale IDs as a comma-separated string, not as multiple form fields with the same name. This is documented in Smartling's API but easy to misinterpret.

## Prevention

- Read API documentation carefully for multi-value parameters
- Add unit tests that verify exact form field format
- Log request bodies during development to verify format

## Related Issues

No related issues documented yet.
