# GTFS Alerts Translation Lambda Terraform Module

This module provisions an AWS Lambda function that translates GTFS-Realtime ServiceAlerts feeds using the Smartling API.

## Features

- **Secure Secret Management**: Provisions an AWS Secrets Manager secret for Smartling credentials. The Lambda fetches this secret at runtime.
- **Flexible Triggers**: Supports both scheduled (cron) triggers and S3 event-based triggers.
- **Granular Permissions**: IAM policies are strictly scoped to the destination bucket/path and the source bucket (if using S3 triggers).
- **Deterministic Builds**: Integrated with `mise` to produce stable, reproducible deployment packages.

## Usage

```hcl
module "gtfs_translator" {
  source = "./terraform"

  function_name         = "gtfs-alerts-translator"
  smartling_user_id     = "your-user-id"
  smartling_account_uid = "your-account-uid"
  
  destination_bucket_name = "mbta-gtfs-feeds"
  destination_paths       = ["realtime/alerts-translated.pb", "realtime/alerts-translated.json"]

  trigger = {
    type                = "cron"
    schedule_expression = "rate(5 minutes)"
    source_url          = "https://example.com/alerts.pb"
  }

  tags = {
    Project = "GTFS-Translation"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| `function_name` | Name of the Lambda function | `string` | `"gtfs-alerts-translator"` | no |
| `smartling_user_id` | Smartling User ID | `string` | n/a | yes |
| `smartling_account_uid` | Smartling Account UID | `string` | n/a | yes |
| `destination_bucket_name` | S3 bucket where translated feeds will be stored | `string` | n/a | yes |
| `destination_paths` | S3 paths/keys within the bucket | `list(string)` | n/a | yes |
| `target_languages` | List of target languages | `list(string)` | `["es", "pt-BR", "ht", "zh-CN", "vi", "zh-TW"]` | no |
| `trigger` | Trigger configuration (type 'cron' or 's3') | `object` | See `variables.tf` | no |
| `lambda_timeout` | Lambda timeout in seconds | `number` | `60` | no |
| `lambda_memory_size` | Lambda memory size in MB | `number` | `512` | no |
| `tags` | Resource tags | `map(string)` | `{}` | no |

### Trigger Object Schema

- `type`: Either `"cron"` or `"s3"`.
- `schedule_expression`: (Required for `cron`) e.g., `"rate(1 minute)"` or `"cron(0 20 * * ? *)"`.
- `source_url`: (Required for `cron`) Default HTTP feed URL for GTFS-RT alerts.
- `bucket_name`: (Required for `s3`) The name of the bucket to monitor.
- `prefix`: (Optional for `s3`) Filter events by object prefix.

## Outputs

| Name | Description |
|------|-------------|
| `lambda_function_arn` | ARN of the Lambda function |
| `lambda_role_arn` | ARN of the IAM role used by the Lambda |
| `secret_arn` | ARN of the Smartling user secret in Secrets Manager |
