#!/bin/bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?"PROJECT_ID is required"}
REGION=${REGION:-us-west1}
IMAGE=gcr.io/$PROJECT_ID/telegram-ai-bot
SERVICE_ACCOUNT_NAME=${SERVICE_ACCOUNT_NAME:-pubsub-invoker}
WEBHOOK_SERVICE=telegram-ai-webhook
WORKER_SERVICE=telegram-ai-worker
TOPIC_NAME=${PUBSUB_TOPIC:-telegram-updates}
SUBSCRIPTION_NAME=${PUBSUB_SUBSCRIPTION:-telegram-updates-push}
DEAD_LETTER_TOPIC_NAME=${PUBSUB_DEAD_LETTER_TOPIC:-telegram-updates-dlq}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PATH="$REPO_ROOT/gcloud/google-cloud-sdk/bin:$PATH"

# Build container

gcloud builds submit --tag "$IMAGE" .

# Create Pub/Sub topic (idempotent)
gcloud pubsub topics create "$TOPIC_NAME" || true
# Create dead-letter topic (idempotent)
gcloud pubsub topics create "$DEAD_LETTER_TOPIC_NAME" || true

TG_TOKEN_SECRET="telegram-token:latest"
OPENAI_SECRET="openai-key:latest"
WEBHOOK_SECRET="webhook-secret:latest"

# Deploy webhook service

gcloud run deploy "$WEBHOOK_SERVICE" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --max-instances=1 \
  --concurrency=1 \
  --memory=512Mi \
  --set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET,WEBHOOK_SECRET=$WEBHOOK_SECRET" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,CHAT_ID=$CHAT_ID,REPLY_CHAT_ID=$REPLY_CHAT_ID,PUBSUB_TOPIC=$TOPIC_NAME"

# Deploy worker service

gcloud run deploy "$WORKER_SERVICE" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --concurrency=1 \
  --memory=512Mi \
  --set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET,WEBHOOK_SECRET=$WEBHOOK_SECRET" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,CHAT_ID=$CHAT_ID,REPLY_CHAT_ID=$REPLY_CHAT_ID,PUBSUB_TOPIC=$TOPIC_NAME,SKIP_PUBSUB_AUTH=true" \
  --command "gunicorn" \
  --args=-b,0.0.0.0:8080,app.worker:app

# Create service account for Pub/Sub push auth (idempotent)
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name="Pub/Sub Invoker" || true

SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
PUBSUB_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$DEAD_LETTER_TOPIC_NAME" \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher" || true

# Allow Pub/Sub to invoke the worker service
gcloud run services add-iam-policy-binding "$WORKER_SERVICE" \
  --region "$REGION" \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/run.invoker"

# Create push subscription to worker with OIDC token
WORKER_URL=$(gcloud run services describe "$WORKER_SERVICE" --region "$REGION" --format='value(status.url)')

gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
  --topic="$TOPIC_NAME" \
  --push-endpoint="$WORKER_URL/pubsub/push" \
  --push-auth-service-account="$SERVICE_ACCOUNT_EMAIL" \
  --ack-deadline=60 \
  --dead-letter-topic="$DEAD_LETTER_TOPIC_NAME" \
  --max-delivery-attempts=3 || true

# Register Telegram webhook
WEBHOOK_URL=$(gcloud run services describe "$WEBHOOK_SERVICE" --region "$REGION" --format='value(status.url)')
TG_TOKEN_VALUE=$(gcloud secrets versions access latest --secret="telegram-token")
WEBHOOK_SECRET_VALUE=$(gcloud secrets versions access latest --secret="webhook-secret")

curl -sS -X POST "https://api.telegram.org/bot${TG_TOKEN_VALUE}/setWebhook" \
  -d "url=${WEBHOOK_URL}/telegram/webhook" \
  -d "secret_token=${WEBHOOK_SECRET_VALUE}" > /dev/null
