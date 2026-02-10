variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region for Cloud Run and Pub/Sub push binding."
  default     = "us-central1"
}

variable "image" {
  type        = string
  description = "Container image to deploy to Cloud Run."
}

variable "webhook_service_name" {
  type        = string
  description = "Cloud Run service name for the webhook."
  default     = "telegram-ai-webhook"
}

variable "worker_service_name" {
  type        = string
  description = "Cloud Run service name for the worker."
  default     = "telegram-ai-worker"
}

variable "chat_id" {
  type        = number
  description = "Telegram chat ID to ingest."
}

variable "reply_chat_id" {
  type        = number
  description = "Telegram chat ID to post replies to."
  default     = null
}

variable "pubsub_audience" {
  type        = string
  description = "Pub/Sub push audience value (optional)."
  default     = ""
}

variable "log_level" {
  type        = string
  description = "Application log level."
  default     = "INFO"
}

variable "firestore_project_id" {
  type        = string
  description = "Firestore project override (optional)."
  default     = ""
}

variable "bot_username" {
  type        = string
  description = "Telegram bot username (optional)."
  default     = ""
}

variable "bot_user_id" {
  type        = number
  description = "Telegram bot user ID (optional)."
  default     = null
}

variable "skip_pubsub_auth" {
  type        = bool
  description = "Skip Pub/Sub auth verification in worker."
  default     = true
}

variable "pubsub_topic" {
  type        = string
  description = "Pub/Sub topic name for Telegram updates."
  default     = "telegram-updates"
}

variable "pubsub_subscription" {
  type        = string
  description = "Pub/Sub push subscription name."
  default     = "telegram-updates-push"
}

variable "worker_url" {
  type        = string
  description = "Cloud Run worker URL (e.g., https://...run.app). Leave empty to skip subscription creation."
  default     = ""
}

variable "firestore_location" {
  type        = string
  description = "Firestore database location."
  default     = "us-central1"
}

variable "pubsub_invoker_sa" {
  type        = string
  description = "Service account id for Pub/Sub push auth."
  default     = "pubsub-invoker"
}

variable "tg_token_secret_name" {
  type        = string
  description = "Secret Manager secret name for Telegram token."
  default     = "telegram-token"
}

variable "openai_key_secret_name" {
  type        = string
  description = "Secret Manager secret name for OpenAI key."
  default     = "openai-key"
}

variable "webhook_secret_name" {
  type        = string
  description = "Secret Manager secret name for webhook secret."
  default     = "webhook-secret"
}

variable "enable_apis" {
  type        = bool
  description = "Enable required Google Cloud APIs."
  default     = true
}
