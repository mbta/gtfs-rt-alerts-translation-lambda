---
module: Documentation
date: 2026-02-25
problem_type: documentation_gap
component: documentation
symptoms:
  - "AGENTS.md references AWS SAM but project uses Terraform"
  - "Environment variables list incomplete"
  - "Project structure outdated"
root_cause: inadequate_documentation
resolution_type: documentation_update
severity: low
tags: [documentation, agents-md, terraform, architecture]
---

# Troubleshooting: AGENTS.md Out of Sync with Architecture

## Problem
The AGENTS.md file contained outdated information about the project's infrastructure and configuration, leading to confusion about actual project setup.

## Environment
- Module: Documentation
- Affected Component: `AGENTS.md`
- Date: 2026-02-25

## Symptoms
- AGENTS.md mentioned AWS SAM (`template.yaml`) but project uses Terraform
- Environment variables list was incomplete
- Missing documentation about language code mapping

## What Didn't Work

**Direct solution:** Review and update AGENTS.md on first pass.

## Solution

Updated AGENTS.md to reflect current architecture:

1. **Infrastructure**: Changed from "AWS SAM" to "Terraform"
2. **CI/CD Pipeline**: Updated `sam build` to `mise run build` + Terraform
3. **Configuration**: Added all current environment variables
4. **Language Code Mapping**: Documented GTFS/Smartling code mapping

**Key changes:**
```markdown
## Architecture Patterns
- **Infrastructure:** AWS Lambda + S3 (defined via Terraform)

## CI/CD Pipeline
5.  **Package:** `mise run build`
6.  **Deploy:** Apply Terraform configuration in `terraform/` directory

## Configuration
- `SMARTLING_USER_SECRET_ARN` - AWS Secrets Manager ARN
- `SMARTLING_JOB_NAME_TEMPLATE` - Template for job names
- `CONCURRENCY_LIMIT` - Max concurrent translation requests
- `LOG_LEVEL` - Logging level

4.  **Language Code Mapping:**
    - GTFS-standard language codes used in configuration and output
    - Automatic mapping to Smartling API codes via `config.py`
```

## Why This Works

Keeping AGENTS.md synchronized with actual architecture ensures:
- New contributors understand the real project structure
- AI assistants get accurate context for making changes
- Less confusion during onboarding and debugging

## Prevention

- Review AGENTS.md after significant architectural changes
- Include AGENTS.md updates in infrastructure change PRs
- Periodically audit documentation for accuracy

## Related Issues

No related issues documented yet.
