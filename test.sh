#!/usr/bin/env bash
# Invoke tests/handler.py through the Lambda Runtime Interface Emulator in a clean
# Lambda image, with the built layer mounted at /opt (as Lambda does).
set -euo pipefail
cd "$(dirname "$0")"
ZIP=dist/gdal-python3.12-x86_64.zip
PORT=${PORT:-9123}

TMP=$(mktemp -d)
unzip -q "$ZIP" -d "$TMP"
CID=$(docker run -d --rm --platform linux/amd64 -p "$PORT:8080" \
  -v "$TMP:/opt:ro" -v "$PWD/tests:/var/task:ro" \
  public.ecr.aws/lambda/python:3.12 handler.handler)
trap 'docker stop "$CID" >/dev/null; rm -rf "$TMP"' EXIT

for _ in $(seq 30); do curl -s -o /dev/null "localhost:$PORT" && break; sleep 0.5; done
RESULT=$(curl -s "localhost:$PORT/2015-03-31/functions/function/invocations" -d '{}')
docker logs "$CID" 2>&1 | grep -vE '^(START|END|REPORT)|RequestId' || true
echo "$RESULT"
echo "$RESULT" | grep -q '"errorMessage"' && { echo "FAILED"; exit 1; } || echo "PASSED"
