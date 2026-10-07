#!/usr/bin/env bash
# Build the GDAL Lambda layer zip (python3.12, x86_64) into ./dist/
set -euo pipefail
cd "$(dirname "$0")"

OUT=dist/gdal-python3.12-x86_64
docker buildx build --platform linux/amd64 \
  --target export --output "type=local,dest=$OUT" .
mv "$OUT/layer.zip" "$OUT.zip" && rmdir "$OUT"
echo "Built $OUT.zip ($(du -h "$OUT.zip" | cut -f1) zipped, $(unzip -l "$OUT.zip" | tail -1 | awk '{printf "%.0fMB", $1/1048576}') unzipped; limit is 250MB)"
