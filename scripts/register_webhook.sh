#!/bin/bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?-"PROJECT_ID is required"}
REGION=${REGION:-us-central1}
WEBHOOK_SERVICE=${WEBHOOK_SERVICE:-telegram-ai-webhook}
TG_TOKEN_SECRET=${TG_TOKEN_SECRET:-telegram-token}
WEBHOOK_SECRET=${WEBHOOK_SECRET:-webhook-secret}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PATH="$REPO_ROOT/gcloud/google-cloud-sdk/bin:$PATH"

WEBHOOK_URL=$(gcloud run services describe "$WEBHOOK_SERVICE" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
TG_TOKEN_VALUE=$(gcloud secrets versions access latest --secret="$TG_TOKEN_SECRET" --project "$PROJECT_ID")
WEBHOOK_SECRET_VALUE=$(gcloud secrets versions access latest --secret="$WEBHOOK_SECRET" --project "$PROJECT_ID")

curl -sS -X POST "https://api.telegram.org/bot${TG_TOKEN_VALUE}/setWebhook" \
  -d "url=${WEBHOOK_URL}/telegram/webhook" \
  -d "secret_token=${WEBHOOK_SECRET_VALUE}"

echo
