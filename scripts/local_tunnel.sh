#!/bin/bash
set -euo pipefail

PORT=${PORT:-8080}

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok is not installed. Please install it first."
  exit 1
fi

ngrok http "$PORT"
