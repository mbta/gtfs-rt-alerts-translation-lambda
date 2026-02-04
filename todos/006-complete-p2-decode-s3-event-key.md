---
status: complete
priority: p2
issue_id: "006"
tags: [reliability, lambda, s3]
dependencies: []
---

# Decode S3 event object keys before building source URL

## Problem Statement

S3 event object keys are URL-encoded. The Lambda handler currently uses the raw key from the
notification to build the S3 URL, which can break when keys contain spaces or special characters.

## Findings

- `gtfs_translation/lambda_handler.py` uses `record["s3"]["object"]["key"]` directly.
- S3 event keys are URL-encoded; keys like `alerts/Service Alert (AM).pb` would be encoded and fail
  to match the actual object key in S3.

## Proposed Solutions

### Option 1: URL-decode keys with `urllib.parse.unquote_plus`

**Approach:** Decode the `key` before building the `s3://` URL.

**Pros:**
- Aligns with AWS guidance for S3 event parsing.
- Low-risk change.

**Cons:**
- Requires an import and small logic update.

**Effort:** Small

**Risk:** Low

---

### Option 2: Use `boto3` event parsing helpers

**Approach:** Use utility functions (if available) to normalize keys before usage.

**Pros:**
- Centralized parsing if expanded later.

**Cons:**
- Adds more boilerplate for a simple case.

**Effort:** Small

**Risk:** Low

## Recommended Action

Decode S3 event object keys with `urllib.parse.unquote_plus` before constructing `source_url` and
add a unit test for a URL-encoded key (spaces or `+`).

## Technical Details

**Affected files:**
- `gtfs_translation/lambda_handler.py` (S3 event parsing)

## Resources

- AWS S3 Event Notifications documentation (URL-encoded keys)

## Acceptance Criteria

- [ ] S3 object keys are decoded before constructing `source_url`.
- [ ] Unit tests cover URL-encoded S3 keys.
- [ ] Tests pass.

## Work Log

### 2026-02-04 - Initial Discovery

**By:** Pi

**Actions:**
- Identified missing URL-decoding for S3 event keys.

**Learnings:**
- Event payloads provide URL-encoded keys that must be normalized to access objects.

### 2026-02-04 - Approved for Work

**By:** Pi Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending → ready
- Ready to be picked up and worked on

**Learnings:**
- Decoding keys aligns with AWS S3 event guidance and prevents missing objects

### 2026-02-04 - Completed

**By:** Pi

**Actions:**
- Decoded S3 event keys with `unquote_plus` in `lambda_handler`
- Added unit test coverage for URL-encoded keys
- Updated todo status to complete

**Learnings:**
- URL-encoded keys with `+` and spaces map correctly after decoding

## Notes

- Add a test case with a key containing spaces or `+`.
- Source: Triage session on 2026-02-04
