---
module: Type Checking
date: 2026-02-04
problem_type: build_error
component: testing_framework
symptoms:
  - "Value of type Collection[str] is not indexable"
  - "mypy error on JSON dictionary access"
  - "Type inference fails for JSON variables"
root_cause: missing_validation
resolution_type: code_fix
severity: low
tags: [mypy, typing, json, collection, type-annotation, tests]
---

# Troubleshooting: Mypy Collection Indexing Error

## Problem
Mypy incorrectly inferred the type of JSON variables as `Collection[str]` instead of `dict[str, Any]`, causing "not indexable" errors when accessing dictionary keys.

## Environment
- Module: Type Checking
- Affected Component: `tests/unit/test_processor.py`
- Date: 2026-02-04

## Symptoms
- mypy error: `Value of type "Collection[str]" is not indexable`
- Tests pass but type checking fails
- Occurs when accessing JSON dictionaries in tests

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt.

## Solution

Add explicit type annotations to JSON variables in tests.

**Code changes:**

```python
# Before (broken):
original_json = processor.to_json(feed)

# After (fixed):
from typing import Any

original_json: dict[str, Any] = processor.to_json(feed)
```

Also update assertions to use safe dictionary access patterns:

```python
# Before:
assert original_json["entity"][0]["alert"]["headerText"]["translation"][0]["text"] == "Test"

# After (more explicit):
entities = original_json.get("entity", [])
assert len(entities) > 0
alert = entities[0].get("alert", {})
# ... etc
```

## Why This Works

1. **Explicit type annotations**: Tells mypy the exact type instead of inferring
2. **Type import**: `Any` from `typing` allows flexible nested structures
3. **Safe access patterns**: `.get()` provides type-safe dictionary access

## Prevention

- Add type annotations to JSON variables in tests
- Use `dict[str, Any]` for parsed JSON structures
- Run `mise run check` (includes mypy) before committing

## Related Issues

No related issues documented yet.
