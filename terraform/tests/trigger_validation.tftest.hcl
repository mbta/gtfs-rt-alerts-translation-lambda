mock_provider "aws" {}

override_data {
  target = data.aws_iam_policy_document.lambda_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

run "cron_requires_source_url" {
  command = plan

  variables {
    smartling_user_id       = "test-user"
    destination_bucket_name = "destination-bucket"
    destination_paths       = ["realtime/alerts.pb"]
    trigger = {
      type                = "cron"
      schedule_expression = "rate(1 minute)"
      source_url          = ""
    }
  }

  expect_failures = [var.trigger]
}

run "s3_requires_bucket_name" {
  command = plan

  providers = {
    aws = aws
  }

  variables {
    smartling_user_id       = "test-user"
    destination_bucket_name = "destination-bucket"
    destination_paths       = ["realtime/alerts.pb"]
    trigger = {
      type        = "s3"
      bucket_name = ""
    }
  }

  expect_failures = [var.trigger]
}
