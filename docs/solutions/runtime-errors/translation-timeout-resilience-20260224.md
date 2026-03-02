---
module: Lambda Handler
date: 2026-02-24
problem_type: runtime_error
component: background_job
symptoms:
  - "Lambda times out waiting for Smartling"
  - "Alerts not published when translation service is slow"
  - "Critical alert data unavailable during translation outages"
root_cause: async_timing
resolution_type: code_fix
severity: critical
tags: [timeout, resilience, smartling, lambda, fault-tolerance]
---

# Troubleshooting: Alerts Not Published When Translation Times Out

## Problem
When Smartling API was slow or unavailable, the Lambda would time out entirely and fail to publish alerts, leaving users without critical transit information.

## Environment
- Module: Lambda Handler
- Affected Component: `gtfs_translation/lambda_handler.py`, `terraform/variables.tf`
- Date: 2026-02-24

## Symptoms
- Lambda function timeouts during Smartling slowdowns
- Alert feeds not updated for extended periods
- Critical transit information unavailable to users

## What Didn't Work

**Direct solution:** The problem was identified and designed with resilience from the start.

## Solution

Implemented a two-tier timeout system:
1. `TRANSLATION_TIMEOUT` - Time to wait for translations (shorter)
2. `LAMBDA_TIMEOUT` - Lambda function timeout (longer)

If translation doesn't complete in time, publish the English-only feed anyway.

**Code changes:**

```python
# gtfs_translation/lambda_handler.py
try:
    translation_successful = True
    metrics = None
    try:
        # Enforce translation timeout to ensure feed is always published
        metrics = await asyncio.wait_for(
            FeedProcessor.process_feed(...),
            timeout=settings.translation_timeout,
        )
        logger.log(NOTICE_LEVEL, "Translation metrics: %s", metrics.to_dict())
    except asyncio.TimeoutError:
        logger.warning(
            "Translation timed out after %s seconds. Publishing feed without translations.",
            settings.translation_timeout,
        )
        translation_successful = False
    except Exception as e:
        logger.exception("Translation failed with error: %s. Publishing feed without translations.", e)
        translation_successful = False

    if not translation_successful:
        # Always upload if translation failed/timed out
        logger.log(NOTICE_LEVEL, "Uploading feed without translations due to translation failure.")
    
    # Upload proceeds regardless of translation success
```

**Terraform configuration:**
```hcl
variable "translation_timeout" {
  type        = number
  default     = 50
  description = "Maximum seconds to wait for translation before publishing without translations"
}

variable "lambda_timeout" {
  type        = number
  default     = 60
  description = "Lambda function timeout in seconds. Must be greater than translation_timeout."
}

# Validation
locals {
  validate_timeouts = var.translation_timeout < var.lambda_timeout ? true : tobool(
    "translation_timeout must be less than lambda_timeout"
  )
}
```

## Why This Works

1. **Graceful degradation**: Users get English alerts rather than nothing
2. **Self-healing**: Next Lambda run will attempt translation again
3. **Separation of concerns**: Translation failure doesn't block alert publishing
4. **Configurable**: Timeouts can be tuned per environment

## Prevention

- Always design for failure of external services
- Use timeouts with graceful degradation
- Validate configuration constraints in infrastructure code
- Test timeout scenarios explicitly

## Related Issues

No related issues documented yet.
