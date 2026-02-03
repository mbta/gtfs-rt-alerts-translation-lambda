variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "gtfs-alerts-translator"
}

variable "smartling_user_id" {
  description = "Smartling User ID"
  type        = string
}

variable "smartling_account_uid" {
  description = "Smartling Account UID"
  type        = string
}

variable "source_url" {
  description = "Default HTTP feed URL for GTFS-RT alerts"
  type        = string
  default     = ""
}

variable "destination_bucket" {
  description = "S3 bucket where translated feeds will be stored"
  type        = string
}

variable "destination_path" {
  description = "S3 path/prefix within the bucket"
  type        = string
}

variable "target_languages" {
  description = "List of target languages"
  type        = list(string)
  default     = ["ES", "PT-BR", "HT", "ZH-CN", "VI", "ZH-TW"]
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB"
  type        = number
  default     = 512
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
