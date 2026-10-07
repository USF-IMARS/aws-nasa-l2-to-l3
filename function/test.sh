#!/usr/bin/env bash
# Run the function's unit tests inside a clean Lambda python3.12 image, with
# the built GDAL layer mounted at /opt as Lambda does. Build the layer first
# (../layer/build.sh).
set -euo pipefail
cd "$(dirname "$0")"
ZIP=../layer/dist/gdal-python3.12-x86_64.zip

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP"
docker run --rm --platform linux/amd64 -v "$TMP:/opt:ro" -v "$PWD:/var/task:ro" \
  -e PYTHONPATH=/var/task/src:/var/task/tests:/opt/python -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python3 public.ecr.aws/lambda/python:3.12 -m unittest discover -s tests -v
