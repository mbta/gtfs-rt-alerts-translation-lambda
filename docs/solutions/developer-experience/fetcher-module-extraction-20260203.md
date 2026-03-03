---
module: Core Architecture
date: 2026-02-03
problem_type: developer_experience
component: service_object
symptoms:
  - "Circular import when importing from lambda_handler"
  - "Scripts cannot reuse fetch functions"
  - "Code duplication between lambda_handler and scripts"
root_cause: missing_workflow_step
resolution_type: code_fix
severity: medium
tags: [architecture, circular-import, refactoring, fetcher, module-extraction]
---

# Troubleshooting: Extract Fetcher Module to Avoid Circular Dependencies

## Problem
The `lambda_handler.py` module contained fetch and secret resolution logic that scripts needed to reuse, but importing from it caused circular dependencies or unwanted side effects.

## Environment
- Module: Core Architecture
- Affected Component: `gtfs_translation/lambda_handler.py`, `gtfs_translation/core/fetcher.py`
- Date: 2026-02-03

## Symptoms
- Circular import errors when scripts import from lambda_handler
- Code duplication between lambda_handler and local run scripts
- Difficulty testing fetch logic in isolation

## What Didn't Work

**Attempted Solution 1:** Import fetch functions directly from lambda_handler in scripts
- **Why it failed:** Caused circular dependencies or imported unwanted Lambda-specific code

## Solution

Extract I/O and secret resolution functions into a new `gtfs_translation/core/fetcher.py` module.

**Code changes:**

```python
# gtfs_translation/core/fetcher.py

import os
import json
import aioboto3
import httpx
from gtfs_translation.config import settings

async def resolve_secrets() -> None:
    """Resolve secrets from AWS Secrets Manager if ARN is provided."""
    # Implementation...

def get_s3_parts(url: str) -> tuple[str, str]:
    """Parse S3 URL into bucket and key."""
    # Implementation...

async def fetch_source(url: str) -> tuple[bytes, str]:
    """Fetch content from S3 or HTTP URL."""
    # Implementation...

async def fetch_old_feed(url: str) -> bytes | None:
    """Fetch previous feed version for diff calculation."""
    # Implementation...
```

Update lambda_handler to import from fetcher:

```python
# gtfs_translation/lambda_handler.py

from gtfs_translation.core.fetcher import (
    resolve_secrets,
    get_s3_parts,
    fetch_source,
    fetch_old_feed,
)
```

Update scripts to use the shared module:

```python
# scripts/run_local.py

from gtfs_translation.core.fetcher import fetch_source
```

## Why This Works

1. **Single responsibility**: fetcher.py handles I/O, lambda_handler handles event routing
2. **Reusability**: Scripts can import fetch functions without Lambda dependencies
3. **Testability**: Fetch logic can be tested in isolation
4. **No circular imports**: Clean dependency graph

## Prevention

- Keep Lambda handlers thin - extract reusable logic to core modules
- Follow single responsibility principle for modules
- Design for reusability from the start when logic will be shared

## Related Issues

No related issues documented yet.
