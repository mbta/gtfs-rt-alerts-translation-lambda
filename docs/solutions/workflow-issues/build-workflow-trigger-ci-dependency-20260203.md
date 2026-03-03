---
module: CI/CD
date: 2026-02-03
problem_type: workflow_issue
component: development_workflow
symptoms:
  - "Build job runs even when CI fails"
  - "Build artifacts created for broken code"
  - "Wasted compute on failed branches"
root_cause: missing_workflow_step
resolution_type: config_change
severity: medium
tags: [github-actions, workflow-run, ci-cd, build, dependency]
---

# Troubleshooting: Build Workflow Should Depend on CI Success

## Problem
The build workflow was running on every push, regardless of whether CI tests passed. This wasted compute and could create build artifacts from broken code.

## Environment
- Module: CI/CD
- Affected Component: `.github/workflows/build.yml`
- Date: 2026-02-03

## Symptoms
- Build job runs even when tests fail
- Build artifacts created for code that doesn't pass checks
- Unnecessary GitHub Actions minutes consumed

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt.

## Solution

Changed the build workflow to use `workflow_run` trigger instead of `push`, and added a condition to only run if CI succeeded.

**Code changes:**

```yaml
# .github/workflows/build.yml

name: Build

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    steps:
      # ... build steps
```

## Why This Works

1. **workflow_run trigger**: Waits for the CI workflow to complete before triggering
2. **conclusion check**: Only proceeds if CI was successful
3. **branch filter**: Only runs for the main branch to avoid building feature branches

## Prevention

- Use `workflow_run` triggers for dependent workflows
- Always add success conditions when chaining workflows
- Document workflow dependencies in README or CONTRIBUTING

## Related Issues

No related issues documented yet.
