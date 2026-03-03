---
module: CI/CD
date: 2026-02-03
problem_type: build_error
component: testing_framework
symptoms:
  - "Tests fail in CI with botocore region error"
  - "S3 and Secrets Manager clients require region"
  - "Tests pass locally but fail in GitHub Actions"
root_cause: config_error
resolution_type: config_change
severity: medium
tags: [ci, botocore, aws, region, github-actions, testing]
---

# Troubleshooting: Botocore Region Required in CI

## Problem
Tests were failing in GitHub Actions CI because `botocore` (the AWS SDK underlying `boto3`) requires a region to be specified when initializing S3 and Secrets Manager clients, even when mocked.

## Environment
- Module: CI/CD
- Affected Component: `.github/workflows/ci.yml`
- Date: 2026-02-03

## Symptoms
- Tests pass locally (where `~/.aws/config` may have a default region)
- Tests fail in CI with region-related errors from botocore
- S3 and Secrets Manager client initialization fails

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt after analyzing CI logs.

## Solution

Set `AWS_DEFAULT_REGION` environment variable in the CI workflow test step.

**Code changes:**

```yaml
# .github/workflows/ci.yml

- name: Run tests
  env:
    AWS_DEFAULT_REGION: us-east-1
  run: mise run test
```

## Why This Works

1. **Botocore requirement**: The AWS SDK requires a region even when endpoints are mocked
2. **CI environment**: Unlike local development, CI runners don't have AWS config files
3. **Environment variable**: `AWS_DEFAULT_REGION` provides the fallback region botocore needs

## Prevention

- Always set `AWS_DEFAULT_REGION` in CI workflows that use AWS SDK
- Consider adding this to project documentation for CI setup
- Include AWS environment variables in CI workflow templates

## Related Issues

No related issues documented yet.
