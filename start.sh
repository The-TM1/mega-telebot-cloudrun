#!/bin/bash
set -e
# Start the local Bot API server (port 8081)
telegram-bot-api \
  --api-id="$TG_API_ID" \
  --api-hash="$TG_API_HASH" \
  --local \
  --http-port=8081 \
  --dir=/tmp/botapi-data &
# Give it a few seconds to initialize
sleep 5
# Start the FastAPI web app (port 8080)
uvicorn main:app --host 0.0.0.0 --port 8080
