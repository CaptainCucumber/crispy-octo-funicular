output "firestore_database" {
  value       = google_firestore_database.default.name
  description = "Firestore database name."
}

output "pubsub_topic" {
  value       = google_pubsub_topic.updates.name
  description = "Pub/Sub topic name."
}

output "pubsub_subscription" {
  value       = var.worker_url != "" ? google_pubsub_subscription.push[0].name : null
  description = "Pub/Sub subscription name (if created)."
}

output "pubsub_invoker_service_account" {
  value       = google_service_account.pubsub_invoker.email
  description = "Service account email for Pub/Sub push auth."
}

output "webhook_url" {
  value       = google_cloud_run_service.webhook.status[0].url
  description = "Cloud Run webhook URL."
}

output "worker_url" {
  value       = google_cloud_run_service.worker.status[0].url
  description = "Cloud Run worker URL."
}
