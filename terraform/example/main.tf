terraform {
  backend "local" {
    path = "/tmp/gtfs-rt-alerts-translation-lambda.tfstate"
  }
}

provider "aws" {
  region = "us-east-2"
}

locals {
  tags = {
    Terraform = "true"
    Project   = "gtfs-rt-alerts-translation-lambda"
  }

  destination_paths = ["alerts/Alerts_enhanced.json", "alerts/Alerts.pb"]
}

resource "aws_s3_bucket" "test_bucket" {
  bucket_prefix = "mbta-gtfs-translation-example-"
  force_destroy = true
  tags          = local.tags
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
  destination_paths       = local.destination_paths

  smartling_user_id     = var.smartling_user_id
  smartling_account_uid = var.smartling_account_uid
  smartling_project_id  = var.smartling_project_id
  target_languages      = ["es-419", "ht-HT"]
  log_level             = "INFO"
  tags                  = local.tags

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

variable "smartling_project_id" {
  type    = string
  default = ""
}

variable "smartling_user_secret" {
  type      = string
  sensitive = true
}
