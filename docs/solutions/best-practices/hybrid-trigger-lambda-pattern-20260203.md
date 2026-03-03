---
module: Architecture
date: 2026-02-03
problem_type: best_practice
component: tooling
symptoms:
  - "Need Lambda to work with both S3 events and scheduled triggers"
  - "Same code should handle push and pull patterns"
  - "Configuration vs event-driven source selection"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [lambda, architecture, s3, eventbridge, trigger, pattern, hybrid]
---

# Best Practice: Hybrid Trigger Lambda Pattern

## Problem
The Lambda needed to support two different trigger patterns:
1. **S3 Push**: React to files landing in S3 (event-driven)
2. **Scheduled Pull**: Fetch from a configured URL on a schedule

## Environment
- Module: Architecture
- Affected Component: `gtfs_translation/lambda_handler.py`
- Date: 2026-02-03

## Solution: Event-Aware but Config-Driven

Design the handler to be **"Event-Aware but Config-Driven"**:

1. **Default**: Look for `SOURCE_URL` in environment variables
2. **Override**: If an S3 event payload is detected, use that specific S3 object instead

**Code pattern:**

```python
# gtfs_translation/lambda_handler.py

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler supporting both S3 events and scheduled triggers."""
    
    # Check if this is an S3 event
    if "Records" in event and event["Records"]:
        record = event["Records"][0]
        if record.get("eventSource") == "aws:s3":
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]
            source_url = f"s3://{bucket}/{key}"
            logger.info("S3 trigger detected", bucket=bucket, key=key)
    else:
        # Fall back to configured SOURCE_URL
        source_url = settings.source_url
        logger.info("Scheduled trigger, using configured source", url=source_url)
    
    # Process the feed from the determined source
    return asyncio.run(_process_feed(source_url))
```

## Why This Works

1. **Flexibility**: Same Lambda code works for both trigger patterns
2. **Simplicity**: No separate handlers or configuration switches
3. **Testability**: Easy to test both paths by constructing different events
4. **Cost efficiency**: One Lambda deployment serves multiple use cases

## Configuration Examples

**S3 Event Trigger (Push):**
- Configure S3 bucket notification to invoke Lambda on object creation
- Lambda reads the bucket/key from the event

**EventBridge Schedule (Pull):**
- Configure EventBridge rule with cron expression
- Lambda reads `SOURCE_URL` from environment

**Environment Variables:**
```
SOURCE_URL=https://api.example.com/alerts.pb
DESTINATION_BUCKET_URLS=s3://output-bucket/alerts-es.pb
TARGET_LANGUAGES=es-419,fr,pt
```

## Prevention

- Document both trigger patterns in README
- Include example Terraform for both S3 and EventBridge triggers
- Test both event shapes in integration tests

## Related Issues

No related issues documented yet.
