variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "gtfs-alerts-translator"
}

variable "is_temporary" {
  description = "Whether resources should be configured for easy cleanup"
  type        = bool
  default     = false
}

variable "smartling_user_id" {
  description = "Smartling User ID"
  type        = string
}

variable "smartling_account_uid" {
  description = "Smartling Account UID"
  type        = string
  default     = ""
}

variable "smartling_project_id" {
  description = "Smartling Project ID"
  type        = string
  default     = ""
}

variable "smartling_job_name_template" {
  description = "Smartling Job nameTemplate value"
  type        = string
  default     = null
}

variable "destination_bucket_name" {
  description = "S3 bucket where translated feeds will be stored"
  type        = string
}

variable "destination_paths" {
  description = "S3 paths/keys within the bucket"
  type        = list(string)
}

variable "target_languages" {
  description = "List of target languages"
  type        = list(string)
  default     = ["es-LA", "pt-BR", "fr-FR", "ht-HT", "zh-CN", "vi-VN", "zh-TW"]
}

variable "trigger" {
  description = "Trigger configuration for the Lambda. Can be type 'cron' with 'schedule_expression' and 'source_url', or type 's3' with 'bucket_name' and optional 'prefix'."
  type = object({
    type                = string
    schedule_expression = optional(string)
    source_url          = optional(string)
    bucket_name         = optional(string)
    prefix              = optional(string)
  })
  default = {
    type                = "cron"
    schedule_expression = "rate(1 minute)"
    source_url          = ""
  }

  validation {
    condition     = contains(["cron", "s3"], var.trigger.type)
    error_message = "Trigger type must be either 'cron' or 's3'."
  }

  validation {
    condition = (
      var.trigger.type != "cron" || (
        var.trigger.source_url != null &&
        trimspace(var.trigger.source_url) != ""
      )
    )
    error_message = "For cron triggers, trigger.source_url must be set."
  }

  validation {
    condition = (
      var.trigger.type != "s3" || (
        var.trigger.bucket_name != null &&
        trimspace(var.trigger.bucket_name) != ""
      )
    )
    error_message = "For s3 triggers, trigger.bucket_name must be set."
  }
}

variable "log_level" {
  description = "Lambda log level"
  type        = string
  default     = "NOTICE"
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

variable "lambda_architectures" {
  description = "Lambda architecture list (e.g., [\"arm64\"], [\"x86_64\"])"
  type        = list(string)
  default     = ["arm64"]
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
