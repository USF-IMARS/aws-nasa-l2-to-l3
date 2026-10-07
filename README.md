# GDAL Lambda layer (Python)

An AWS Lambda layer that provides GDAL and its Python bindings (`from osgeo import gdal, ogr, osr, gdal_array`).
It targets the **python3.12** runtime on **x86_64**.

It bundles:

| Component | Version | Notes |
|---|---|---|
| GDAL + `osgeo` bindings | 3.13.3 | CLI tools too (`/opt/bin/gdalinfo`, `gdal_translate`, `gdalwarp`, …) |
| PROJ | 9.9.0 | `proj.db` at `/opt/share/proj` |
| GEOS | 3.13 (AL2023 system package) | |
| HDF5 | 1.14.6 | GDAL `HDF5` driver |
| NetCDF-C | 4.9.3 | GDAL `netCDF` driver |
| numpy | 2.x (latest at build time) | needed for `ReadAsArray`/`gdal_array` |

Lambda mounts layers at `/opt`, and everything here is installed under `/opt`, so you **don't need to set any environment variables**.
`/opt/lib` is already on `LD_LIBRARY_PATH` and `/opt/python` is on `sys.path`.
GDAL and PROJ find their data files through the compiled-in `/opt/share/...` paths.

## Build

You need Docker with buildx.

```bash
./build.sh   # -> dist/gdal-python3.12-x86_64.zip
```

## Test locally

```bash
./test.sh   # runs tests/handler.py in a clean Lambda image with the layer mounted at /opt
```

## Publish

Upload the zip through S3 (direct uploads are capped at 50 MB):

```bash
aws s3 cp dist/gdal-python3.12-x86_64.zip s3://MY-BUCKET/layers/
aws lambda publish-layer-version \
  --layer-name gdal-python312 \
  --content S3Bucket=MY-BUCKET,S3Key=layers/gdal-python3.12-x86_64.zip \
  --compatible-runtimes python3.12 \
  --compatible-architectures x86_64
```

Then attach the returned `LayerVersionArn` to your function.
The layer is ~40 MB zipped and ~119 MB unzipped (with numpy). That unzipped size counts toward Lambda's 250 MB limit, together with your function and any other layers.

## Notes

- The layer already provides numpy, so don't package numpy in your function.
- Reading from S3 directly works via `/vsis3/bucket/key` and uses the function's IAM role credentials.
- Write scratch files to `/tmp` (the only writable path).
