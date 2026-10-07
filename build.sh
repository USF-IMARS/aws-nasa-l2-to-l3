#!/usr/bin/env bash
# Build the GDAL Lambda layer zip into ./dist/
#   PYTHON_VERSION=3.12 ARCH=x86_64 ./build.sh     (ARCH: x86_64 | arm64)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_VERSION=${PYTHON_VERSION:-3.12}
ARCH=${ARCH:-x86_64}
case "$ARCH" in
  x86_64) PLATFORM=linux/amd64 ;;
  arm64)  PLATFORM=linux/arm64 ;;
  *) echo "ARCH must be x86_64 or arm64" >&2; exit 1 ;;
esac

OUT=dist/gdal-python${PYTHON_VERSION}-${ARCH}
docker buildx build --platform "$PLATFORM" \
  --build-arg PYTHON_VERSION="$PYTHON_VERSION" \
  ${INCLUDE_NUMPY:+--build-arg INCLUDE_NUMPY="$INCLUDE_NUMPY"} \
  --target export --output "type=local,dest=$OUT" .
mv "$OUT/layer.zip" "$OUT.zip" && rmdir "$OUT"
echo "Built $OUT.zip ($(du -h "$OUT.zip" | cut -f1) zipped, $(unzip -l "$OUT.zip" | tail -1 | awk '{printf "%.0fMB", $1/1048576}') unzipped; limit is 250MB)"
