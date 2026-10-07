#!/usr/bin/env bash
# Package src/l2_to_l3 and upload it to an existing Lambda function.
#   FUNCTION_NAME=l2-to-l3 ./deploy.sh
# See README.md for creating the function the first time.
set -euo pipefail
cd "$(dirname "$0")"
: "${FUNCTION_NAME:?set FUNCTION_NAME}"
REGION=${AWS_REGION:-us-west-2}

mkdir -p dist && rm -f dist/function.zip
(cd src && zip -qr ../dist/function.zip l2_to_l3 -x '*/__pycache__/*')
aws lambda update-function-code --region "$REGION" --function-name "$FUNCTION_NAME" \
  --zip-file fileb://dist/function.zip --query '[FunctionName,LastModified,CodeSize]' --output text
