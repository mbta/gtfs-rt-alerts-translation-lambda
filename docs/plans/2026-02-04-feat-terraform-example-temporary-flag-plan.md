---
title: feat: Create Terraform example and add temporary resource support
type: feat
date: 2026-02-04
---

# feat: Create Terraform example and add temporary resource support

## Overview
This feature adds an `is_temporary` toggle to the core Terraform module to facilitate ephemeral testing environments and provides a turnkey example for deploying the GTFS translator.

## Problem Statement / Motivation
When testing the infrastructure or setting up temporary staging environments, AWS Secrets Manager defaults to a 30-day recovery window upon deletion. This prevents the immediate reuse of the secret name if the stack is torn down and rebuilt. Additionally, developers need a reference example that demonstrates how to wire the module to a real-world feed like the MBTA Alerts.

## Proposed Solution

1.  **Module Enhancement:**
    - Update `terraform/variables.tf` to include an `is_temporary` boolean (default false).
    - Update `terraform/main.tf` to set `recovery_window_in_days` on the `aws_secretsmanager_secret` to 0 if `is_temporary` is true (allowing immediate deletion).
2.  **Example Implementation:**
    - Provide a complete `terraform/example/` directory.
    - Create a public-access S3 bucket with `force_destroy` enabled so it can be wiped easily.
    - Configure the Lambda to pull from the MBTA enhanced alerts JSON feed every minute.
    - Use `aws_secretsmanager_secret_version` in the example to populate the module's secret from the user's `.tfvars`.

## Technical Considerations

- **Secrets Manager:** Note that setting `recovery_window_in_days` to 0 requires the `secretsmanager:DeleteSecret` permission with `ForceDeleteWithoutRecovery` (or similar depending on provider version).
- **S3 Public Access:** The example will explicitly disable "Block Public Access" settings at the bucket level and attach a public-read policy to satisfy the "public-access-s3 bucket" requirement.
- **Tofu/Terraform Version:** The code will be compatible with OpenTofu 1.x / Terraform 1.x.

## Acceptance Criteria

- [x] `terraform/variables.tf` includes `is_temporary` (boolean, default false).
- [x] `aws_secretsmanager_secret` in `terraform/main.tf` sets `recovery_window_in_days = 0` when `is_temporary` is true, else defaults to 30.
- [x] `terraform/example/main.tf` is created and configured for `us-east-2`.
- [x] `terraform/example/main.tf` includes an `aws_secretsmanager_secret_version` resource to populate the secret.
- [x] Example uses `https://cdn.mbta.com/realtime/Alerts_enhanced.json` as `source_url`.
- [x] Example trigger is set to `rate(1 minute)`.
- [x] Example creates an S3 bucket with `force_destroy = true`.
- [x] Example includes `aws_s3_bucket_public_access_block` and `aws_s3_bucket_policy` for public readability.
- [x] Example outputs the destination bucket name and the Lambda ARN.
- [ ] `tofu -destroy` successfully removes all resources including the S3 bucket even if it contains translated feed files.
- [x] `.gitignore` updated to ignore `*.tfvars` and `*.tfvars.json` in `terraform/example/`.
- [x] Lambda policy includes `s3:ListBucket` on the destination bucket.
- [x] Module supports configurable log level via `log_level`, defaulting to INFO and set to DEBUG in the example.

## MVP

### terraform/example/terraform.tfvars.example
```hcl
smartling_user_id     = "your-user-id"
smartling_account_uid = "your-account-uid"
smartling_user_secret = "your-secret-value"
```

### terraform/example/main.tf
```hcl
provider "aws" {
  region = "us-east-2"
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "test_bucket" {
  bucket        = "mbta-gtfs-translation-example-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "public_access" {
  bucket = aws_s3_bucket.test_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "public_read" {
  bucket = aws_s3_bucket.test_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicRead"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.test_bucket.arn}/*"
      },
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.public_access]
}

module "gtfs_translator" {
  source = "../"

  is_temporary            = true
  function_name           = "example-gtfs-translator"
  destination_bucket_name = aws_s3_bucket.test_bucket.id
  destination_path        = "alerts/"

  smartling_user_id     = var.smartling_user_id
  smartling_account_uid = var.smartling_account_uid

  trigger = {
    type                = "cron"
    schedule_expression = "rate(1 minute)"
    source_url          = "https://cdn.mbta.com/realtime/Alerts_enhanced.json"
  }
}

resource "aws_secretsmanager_secret_version" "smartling_secret_val" {
  secret_id     = module.gtfs_translator.secret_arn
  secret_string = var.smartling_user_secret
}

variable "smartling_user_id" {
  type = string
}

variable "smartling_account_uid" {
  type = string
}

variable "smartling_user_secret" {
  type      = string
  sensitive = true
}
```

### terraform/example/outputs.tf
```hcl
output "bucket_name" {
  value = aws_s3_bucket.test_bucket.id
}

output "lambda_arn" {
  value = module.gtfs_translator.lambda_function_arn
}
```

## References & Research
- Internal `terraform/main.tf` for existing resource definitions.
- AWS Documentation on `recovery_window_in_days`.
- MBTA GTFS-RT feed documentation.
- Terraform `.gitignore` best practices for `.tfvars`.
