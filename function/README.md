# L2 → L3 function

Builds 8-day Gulf of Mexico composites from NASA OB.DAAC Level-2 ocean color swaths.
By default it uses Aqua MODIS `chlor_a`, the product in `MODISA_L2_OC`.
Each run:

1. Picks an 8-day period. Periods start on day-of-year 1, 9, 17, … like OB.DAAC's own L3 8-day products.
2. Finds every granule intersecting the Gulf (98°W–80°W, 18°N–31°N) in that period, using NASA's CMR search API.
3. Downloads each from `s3://ob-cumulus-prod-public` with temporary Earthdata credentials.
4. Masks fill, out-of-range and flagged pixels using OB.DAAC's default L3 chlorophyll flag list (cloud, land, glint, …).
5. Warps each swath onto a 0.01° lat/lon grid with GDAL's geolocation-array transformer.
6. Averages the swaths pixel by pixel.
7. Writes a 2-band Cloud-Optimized GeoTIFF (band 1 the mean, band 2 the number of swaths per pixel) to
   `s3://$OUTPUT_BUCKET/$OUTPUT_PREFIX/<short_name>/<variable>/<year>/<short_name>.<start>_<end>.L3m.8D.<variable>.GoM.tif`.

## Event

All keys are optional:

```json
{"date": "2025-06-03", "short_name": "MODISA_L2_OC", "variable": "chlor_a"}
```

`date` selects the period containing that day.
Without it, the function composites the most recent complete period, which suits a scheduled run.

## Configuration

| Setting | Value |
|---|---|
| Runtime / architecture | python3.12 / x86_64 (must match the layer) |
| Handler | `l2_to_l3.handler.lambda_handler` |
| Layer | the GDAL layer from `../layer` |
| Region | **us-west-2**. OB.DAAC's temporary S3 credentials only work there. |
| Memory / timeout / ephemeral storage | 2048 MB / 900 s / 2048 MB to start with |
| `OUTPUT_BUCKET` (required) | Bucket for the composites |
| `EDL_SECRET_ID` (required) | Secrets Manager secret holding `{"username": "...", "password": "..."}` for Earthdata Login |
| `OUTPUT_PREFIX` | Default `l3` |
| `SHORT_NAME`, `VARIABLE` | Default `MODISA_L2_OC`, `chlor_a` |
| `RESOLUTION_DEG` | Default `0.01` |

The execution role needs `secretsmanager:GetSecretValue` on the secret and `s3:PutObject` on the output bucket, plus the usual CloudWatch Logs permissions.
Reads from `ob-cumulus-prod-public` use the Earthdata credentials, not the role.

## Test

```bash
./test.sh   # unit tests + GDAL gridding on synthetic swaths, in the Lambda image with the layer at /opt
```

This needs the layer zip built first (`../layer/build.sh`).

## Deploy

```bash
FUNCTION_NAME=l2-to-l3 ./deploy.sh   # updates the code of an existing function
```
