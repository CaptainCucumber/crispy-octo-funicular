#!/bin/bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?"PROJECT_ID is required"}
REGION=${REGION:-us-west1}
IMAGE=gcr.io/$PROJECT_ID/telegram-ai-bot

# Build container

gcloud builds submit --tag "$IMAGE" .

# Create Pub/Sub topic (idempotent)
gcloud pubsub topics create telegram-updates || true

TG_TOKEN_SECRET="projects/$PROJECT_ID/secrets/telegram-token:latest"
OPENAI_SECRET="projects/$PROJECT_ID/secrets/openai-key:latest"
WEBHOOK_SECRET="projects/$PROJECT_ID/secrets/webhook-secret:latest"

# Deploy webhook service

gcloud run deploy telegram-ai-webhook \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated=false \
  --max-instances=1 \
  --concurrency=1 \
  --memory=512Mi \
  --set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET,WEBHOOK_SECRET=$WEBHOOK_SECRET" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,CHAT_ID=$CHAT_ID,PUBSUB_TOPIC=telegram-updates" \
  --entry-point app.main:app

# Deploy worker service

gcloud run deploy telegram-ai-worker \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated=false \
  --max-instances=1 \
  --concurrency=1 \
  --memory=512Mi \
  --set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET,WEBHOOK_SECRET=$WEBHOOK_SECRET" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,CHAT_ID=$CHAT_ID,PUBSUB_TOPIC=telegram-updates" \
  --entry-point app.worker:app
