# L2 to L3 on AWS Lambda

A Python Lambda function that processes Level-2 data into Level-3 products, plus the GDAL layer it runs on.

| Folder                   | What it is                                                                                | How often it changes       |
|--------------------------|-------------------------------------------------------------------------------------------|----------------------------|
| [`layer/`](layer/)       | Lambda layer with GDAL, PROJ, GEOS, HDF5, NetCDF and numpy, built from source with Docker | Rarely. The build is slow. |
| [`function/`](function/) | The L2 → L3 processing code (`l2_to_l3` package)                                          | Often. Deploys are fast.   |

The two live in one repo because the function only works with this exact layer: python3.12, x86_64, with numpy and GDAL coming from the layer.
Change them together in one commit when they need to move together, and otherwise build and deploy each on its own.

## Conventions

- **No build output in git.** `dist/` and zips are ignored. `layer/Dockerfile` is the source of truth, and built layer zips live in S3.
- **Every component in the layer is pinned** in `layer/Dockerfile` (GDAL, PROJ, HDF5, NetCDF, numpy), so two builds from the same commit match.
- **Tag layer releases** after publishing, e.g. `layer-v1`, with the GDAL version and the resulting `LayerVersionArn` in the tag message.
- **The function doesn't package numpy or gdal.** They come from the layer, so `function/requirements.txt` must not list them.

More detail: [`layer/README.md`](layer/README.md) for the layer and [`function/README.md`](function/README.md) for the function.

## Deploy (first time)

Everything runs in **us-west-2**, the only region where NASA's temporary S3 credentials work.
That's also why the function isn't run against real data locally; the unit tests (`function/test.sh`) mock NASA and S3 and need no credentials.
You need Docker with buildx and the AWS CLI.

Three sets of credentials are involved:

| Credential                          | Used for                                                                        | Where it lives                                |
|-------------------------------------|---------------------------------------------------------------------------------|-----------------------------------------------|
| **Earthdata Login (EDL)** user/pass | Getting temporary S3 credentials for NASA's bucket                              | A Secrets Manager secret (step 5)             |
| **Your AWS credentials**            | Publishing the layer, creating and deploying the function                       | AWS CLI profile (step 2)                      |
| **Lambda execution role**           | What the function may do in AWS: read the EDL secret, write composites and logs | An IAM role attached to the function (step 6) |

Your EDL password never goes in code, environment variables or git.

1. **Earthdata Login account** (once).
   1. [Register](https://urs.earthdata.nasa.gov/users/new), or [sign in](https://urs.earthdata.nasa.gov/).
   2. Open <https://obdaac-tea.earthdatacloud.nasa.gov/s3credentials> in a browser.
      On first use, EDL asks you to authorize the OB.DAAC application. Approve it.
   3. The page should then show JSON with `accessKeyId`, `secretAccessKey`, `sessionToken` and `expiration`.
      If it does, your account is ready. Don't share that output; those are working credentials for the next hour.

2. **AWS CLI.** Configure it for us-west-2:

   ```bash
   aws configure            # access keys, or: aws configure sso
   aws configure set region us-west-2
   aws sts get-caller-identity   # confirms which account and identity you're using
   ```

   That identity needs permission to:
   - create the bucket (`s3:CreateBucket`, unless it already exists), upload the layer zip (`s3:PutObject`) and publish it (`lambda:PublishLayerVersion`);
   - create and update the function (`lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:InvokeFunction`);
   - create the secret and the role (`secretsmanager:CreateSecret`, `iam:CreateRole`, `iam:PutRolePolicy`, `iam:AttachRolePolicy`, `iam:PassRole`);
   - read the function's logs (`logs:FilterLogEvents`).

   Then set the variables the remaining steps use:

   ```bash
   REGION=us-west-2
   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
   OUTPUT_BUCKET=l2-to-l3          # holds the layer zip (layers/) and the composites (l3/)
   SECRET_NAME=l2-to-l3/earthdata
   ROLE_NAME=l2-to-l3-lambda
   FUNCTION_NAME=l2-to-l3
   ```

3. **Bucket.** Skip this if the bucket already exists:

   ```bash
   aws s3 mb "s3://$OUTPUT_BUCKET" --region "$REGION"
   ```

4. **Build, test and publish the layer.** The first build takes about 15 minutes.

   ```bash
   layer/build.sh && layer/test.sh
   aws s3 cp layer/dist/gdal-python3.12-x86_64.zip "s3://$OUTPUT_BUCKET/layers/" --region "$REGION"
   LAYER_ARN=$(aws lambda publish-layer-version --region "$REGION" \
     --layer-name gdal-python312 \
     --content "S3Bucket=$OUTPUT_BUCKET,S3Key=layers/gdal-python3.12-x86_64.zip" \
     --compatible-runtimes python3.12 --compatible-architectures x86_64 \
     --query LayerVersionArn --output text)
   git tag -a layer-v1 -m "GDAL 3.13.3, $LAYER_ARN"
   ```

5. **Store the Earthdata login** in AWS Secrets Manager.
   The function reads a secret shaped like `{"username": "...", "password": "..."}`.
   This prompts for the password so it stays out of your shell history, writes the JSON to a private temp file, and deletes the file afterwards:

   ```bash
   read -rp "EDL username: " EDL_USER
   read -rsp "EDL password: " EDL_PASS; echo
   SECRET_FILE=$(mktemp)    # created readable only by you
   EDL_USER="$EDL_USER" EDL_PASS="$EDL_PASS" python3 -c \
     'import json, os; print(json.dumps({"username": os.environ["EDL_USER"], "password": os.environ["EDL_PASS"]}))' \
     > "$SECRET_FILE"
   aws secretsmanager create-secret --region "$REGION" --name "$SECRET_NAME" \
     --secret-string "file://$SECRET_FILE" --query ARN --output text
   rm -f "$SECRET_FILE"; unset EDL_PASS
   ```

6. **Create the execution role.**
   It can read only that secret and write only under `l3/` in the bucket.
   Reads from NASA's bucket use the temporary Earthdata credentials, not this role.

   ```bash
   aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document '{
     "Version": "2012-10-17",
     "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
   }'

   aws iam attach-role-policy --role-name "$ROLE_NAME" \
     --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

   aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name l2-to-l3 --policy-document "{
     \"Version\": \"2012-10-17\",
     \"Statement\": [
       {\"Effect\": \"Allow\", \"Action\": \"secretsmanager:GetSecretValue\",
        \"Resource\": \"arn:aws:secretsmanager:$REGION:$ACCOUNT:secret:$SECRET_NAME-*\"},
       {\"Effect\": \"Allow\", \"Action\": \"s3:PutObject\",
        \"Resource\": \"arn:aws:s3:::$OUTPUT_BUCKET/l3/*\"}
     ]
   }"
   ```

   The `-*` on the secret ARN is needed because Secrets Manager appends a random suffix to every secret's ARN.
   If you change `OUTPUT_PREFIX`, change `l3/*` to match.

7. **Test and create the function.**

   ```bash
   function/test.sh
   mkdir -p function/dist
   (cd function/src && zip -qr ../dist/function.zip l2_to_l3 -x '*/__pycache__/*')

   aws lambda create-function --region "$REGION" --function-name "$FUNCTION_NAME" \
     --runtime python3.12 --architectures x86_64 \
     --handler l2_to_l3.handler.lambda_handler \
     --role "arn:aws:iam::$ACCOUNT:role/$ROLE_NAME" \
     --layers "$LAYER_ARN" \
     --memory-size 2048 --timeout 900 --ephemeral-storage Size=2048 \
     --environment "Variables={OUTPUT_BUCKET=$OUTPUT_BUCKET,EDL_SECRET_ID=$SECRET_NAME}" \
     --zip-file fileb://function/dist/function.zip
   ```

   `EDL_SECRET_ID` holds the secret's *name*, not its value.
   If IAM reports that the role can't be assumed yet, wait a few seconds and retry; new roles take a moment to become usable.

8. **Check it end to end.**

   ```bash
   aws lambda invoke --region "$REGION" --function-name "$FUNCTION_NAME" \
     --cli-binary-format raw-in-base64-out --payload '{"date": "2025-06-03"}' /dev/stdout
   aws logs tail "/aws/lambda/$FUNCTION_NAME" --region "$REGION" --since 30m
   ```

   If something fails, see [Troubleshooting](#troubleshooting).

## Updating

- **Function code:** `function/test.sh && FUNCTION_NAME=$FUNCTION_NAME function/deploy.sh`
- **EDL password:** rerun step 5 with `put-secret-value --secret-id "$SECRET_NAME"` in place of `create-secret --name "$SECRET_NAME"`.
  Warm Lambda containers reuse their temporary S3 credentials for up to an hour, so the new password is picked up within an hour.
- **Layer:** rerun step 4 (with the next tag, e.g. `layer-v2`), then point the function at the new version:

  ```bash
  aws lambda update-function-configuration --region "$REGION" \
    --function-name "$FUNCTION_NAME" --layers "$LAYER_ARN"
  ```

## Troubleshooting

| Symptom                                                                 | Likely cause                                                                                                               |
|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| `HTTP Error 401: Unauthorized` while fetching S3 credentials            | Wrong EDL username/password in the secret, or the OB.DAAC application isn't authorized in your EDL profile (deploy step 1) |
| `HTTP ERROR 502` in the browser right after logging in to EDL           | A failure on OB.DAAC's side when EDL sends you back; see below                                                             |
| `AccessDenied` on `GetSecretValue`                                      | The role policy's secret ARN doesn't match, e.g. a different `SECRET_NAME` or region                                       |
| `403 Forbidden` downloading a granule                                   | The function isn't running in us-west-2, or the temporary credentials expired                                              |
| `Anonymous users cannot invoke requests against Requester Pays buckets` | The request was sent without the Earthdata temporary credentials                                                           |
| `AccessDenied` on `PutObject`                                           | The output bucket or prefix doesn't match the role policy                                                                  |

For the 502: retry in a private window, since stale `obdaac-tea` cookies can cause it.
Then check whether another DAAC's credentials page works for the same account, e.g. <https://archive.podaac.earthdata.nasa.gov/s3credentials>.
If only OB.DAAC fails, report it to OB.DAAC on the [Earthdata Forum](https://forum.earthdata.nasa.gov/).
