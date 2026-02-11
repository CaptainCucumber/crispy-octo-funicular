terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.20.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

locals {
  apis = [
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each           = var.enable_apis ? toset(local.apis) : []
  service            = each.value
  disable_on_destroy = false
}

resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  depends_on = [
    google_project_service.required,
  ]
}

data "google_secret_manager_secret_version" "telegram_token" {
  secret  = var.tg_token_secret_name
  version = "latest"

  depends_on = [
    google_project_service.required,
  ]
}

data "google_secret_manager_secret_version" "openai_key" {
  secret  = var.openai_key_secret_name
  version = "latest"

  depends_on = [
    google_project_service.required,
  ]
}

data "google_secret_manager_secret_version" "webhook_secret" {
  secret  = var.webhook_secret_name
  version = "latest"

  depends_on = [
    google_project_service.required,
  ]
}

data "google_secret_manager_secret_version" "instagram_token" {
  secret  = var.instagram_token_secret_name
  version = "latest"

  depends_on = [
    google_project_service.required,
  ]
}

resource "google_pubsub_topic" "updates" {
  name = var.pubsub_topic

  depends_on = [
    google_project_service.required,
  ]
}

resource "google_pubsub_topic" "dead_letter" {
  name = var.pubsub_dead_letter_topic

  depends_on = [
    google_project_service.required,
  ]
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_service_account" "pubsub_invoker" {
  account_id   = var.pubsub_invoker_sa
  display_name = "Pub/Sub Invoker"
}

resource "google_cloud_run_service_iam_member" "worker_invoker" {
  count    = var.worker_service_name != "" ? 1 : 0
  service  = google_cloud_run_service.worker.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

resource "google_pubsub_subscription" "push" {
  count = var.worker_service_name != "" ? 1 : 0

  name  = var.pubsub_subscription
  topic = google_pubsub_topic.updates.name

  ack_deadline_seconds = 360

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  push_config {
    push_endpoint = "${google_cloud_run_service.worker.status[0].url}/pubsub/push"
    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }

  depends_on = [
    google_project_service.required,
    google_pubsub_topic_iam_member.dead_letter_publisher,
  ]
}

resource "google_cloud_run_service" "webhook" {
  name     = var.webhook_service_name
  location = var.region

  template {
    spec {
      containers {
        image = var.image

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CHAT_ID"
          value = tostring(var.chat_id)
        }

        env {
          name  = "PUBSUB_TOPIC"
          value = var.pubsub_topic
        }

        env {
          name  = "LOG_LEVEL"
          value = var.log_level
        }

        env {
          name  = "REPLY_CHAT_ID"
          value = var.reply_chat_id == null ? "" : tostring(var.reply_chat_id)
        }

        env {
          name  = "PUBSUB_AUDIENCE"
          value = var.pubsub_audience
        }

        env {
          name  = "FIRESTORE_PROJECT_ID"
          value = var.firestore_project_id
        }

        env {
          name  = "BOT_USERNAME"
          value = var.bot_username
        }

        env {
          name  = "BOT_USER_ID"
          value = var.bot_user_id == null ? "" : tostring(var.bot_user_id)
        }

        env {
          name = "TG_TOKEN"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.telegram_token.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "OPENAI_KEY"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.openai_key.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "WEBHOOK_SECRET"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.webhook_secret.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "INSTAGRAM_ACCESS_TOKEN"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.instagram_token.secret
              key  = "latest"
            }
          }
        }
      }

      timeout_seconds = 300
    }
  }

  autogenerate_revision_name = true

  depends_on = [
    google_project_service.required,
  ]
}

resource "google_cloud_run_service_iam_member" "webhook_public" {
  service  = google_cloud_run_service.webhook.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_service" "worker" {
  name     = var.worker_service_name
  location = var.region

  template {
    spec {
      containers {
        image = var.image

        command = ["gunicorn"]
        args    = ["-b", "0.0.0.0:8080", "app.worker:app"]

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CHAT_ID"
          value = tostring(var.chat_id)
        }

        env {
          name  = "PUBSUB_TOPIC"
          value = var.pubsub_topic
        }

        env {
          name  = "LOG_LEVEL"
          value = var.log_level
        }

        env {
          name  = "REPLY_CHAT_ID"
          value = var.reply_chat_id == null ? "" : tostring(var.reply_chat_id)
        }

        env {
          name  = "PUBSUB_AUDIENCE"
          value = var.pubsub_audience
        }

        env {
          name  = "SKIP_PUBSUB_AUTH"
          value = var.skip_pubsub_auth ? "true" : "false"
        }

        env {
          name  = "FIRESTORE_PROJECT_ID"
          value = var.firestore_project_id
        }

        env {
          name  = "BOT_USERNAME"
          value = var.bot_username
        }

        env {
          name  = "BOT_USER_ID"
          value = var.bot_user_id == null ? "" : tostring(var.bot_user_id)
        }

        env {
          name = "TG_TOKEN"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.telegram_token.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "OPENAI_KEY"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.openai_key.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "WEBHOOK_SECRET"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.webhook_secret.secret
              key  = "latest"
            }
          }
        }

        env {
          name = "INSTAGRAM_ACCESS_TOKEN"
          value_from {
            secret_key_ref {
              name = data.google_secret_manager_secret_version.instagram_token.secret
              key  = "latest"
            }
          }
        }
      }

      timeout_seconds = 300
    }
  }

  autogenerate_revision_name = true

  depends_on = [
    google_project_service.required,
  ]
}
