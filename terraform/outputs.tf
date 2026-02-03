output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.translation_function.arn
}

output "lambda_role_arn" {
  description = "ARN of the IAM role used by the Lambda"
  value       = aws_iam_role.lambda_role.arn
}

output "secret_arn" {
  description = "ARN of the Smartling user secret"
  value       = aws_secretsmanager_secret.smartling_secret.arn
}
