---
title: Create Terraform module for GTFS Alerts Translation Lambda
type: feat
date: 2026-02-03
---

# Create Terraform module for GTFS Alerts Translation Lambda

## Overview
This plan outlines the creation of a Terraform module to replace the existing AWS SAM template and updates the application to fetch secrets from AWS Secrets Manager at runtime.

## Problem Statement / Motivation
Transitioning to Terraform provides better integration with standard MBTA infrastructure pipelines. Fetching secrets at runtime via ARN is more secure than environment variable injection as it avoids storing secrets in plaintext in `.tfstate` or the AWS Console.

## Proposed Solution
1. Create a Terraform module in `terraform/` managing Lambda, IAM, and Secrets Manager.
2. Update the Python application to fetch the Smartling secret using `boto3` when an ARN is provided.
3. Validate infrastructure security using Checkov.

## Technical Considerations

- **Secrets Manager**: 
  - Module creates `aws_secretsmanager_secret`.
  - Lambda environment variable `SMARTLING_USER_SECRET_ARN` will be set.
  - Lambda IAM role will have `secretsmanager:GetSecretValue` on the specific secret.
- **S3 Permissions**: IAM policies scoped to `destination_bucket` and `destination_path` for `GetObject` and `PutObject`. `s3:ListBucket` is omitted as it is not strictly required.
- **Application Logic**: 
  - `config.py` updated to handle `smartling_user_secret_arn`.
  - `lambda_handler.py` fetches secret value using `boto3` if ARN is present.
- **Network**: Lambda runs outside VPC for direct Smartling API access.
- **Security Validation**: Use `checkov` to scan the `terraform/` directory for security best practices (e.g., encryption at rest, IAM least privilege).

## Acceptance Criteria

- [ ] Terraform module exists in `terraform/`.
- [ ] Module takes `destination_bucket` and `destination_path` as separate inputs.
- [ ] Module creates an `aws_secretsmanager_secret` for the Smartling user secret.
- [ ] Default `target_languages` is `["ES", "PT-BR", "HT", "ZH-CN", "VI", "ZH-TW"]`.
- [ ] Lambda IAM role has `secretsmanager:GetSecretValue` for the created secret.
- [ ] Lambda IAM role has `s3:PutObject` and `s3:GetObject` permissions limited to the specified bucket and path.
- [ ] Python app fetches the secret value from Secrets Manager at startup using `SMARTLING_USER_SECRET_ARN`.
- [ ] `checkov -d terraform/` passes with no high-severity findings (or documented suppressions).

## MVP Structure

### terraform/variables.tf
Inputs: `smartling_user_id`, `smartling_account_uid`, `source_url`, `destination_bucket`, `destination_path`, `target_languages`, `tags`.

### terraform/main.tf
Resources: `aws_secretsmanager_secret`, `aws_iam_role`, `aws_iam_policy`, `aws_lambda_function`, `aws_cloudwatch_log_group`.

### gtfs_translation/config.py
Updated to handle `smartling_user_secret_arn`.

### gtfs_translation/lambda_handler.py
Add logic to fetch secret value from `boto3.client("secretsmanager")`.

- [x] Implement Terraform variables in `terraform/variables.tf`
- [x] Implement Terraform main resources in `terraform/main.tf` (Lambda, IAM, Secrets Manager, CloudWatch)
- [x] Implement Terraform outputs in `terraform/outputs.tf`
- [x] Update `gtfs_translation/config.py` to handle `SMARTLING_USER_SECRET_ARN`
- [x] Update `gtfs_translation/lambda_handler.py` to fetch secret from Secrets Manager at runtime
- [x] Run security validation with Checkov
- [x] Verify functionality (manual check/unit tests)

## References & Research
- [Checkov Documentation](https://www.checkov.io/docs/index.html)
- [AWS Secrets Manager boto3 docs](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager.html#SecretsManager.Client.get_secret_value)
