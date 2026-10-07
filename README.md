# GDAL Lambda layer (Python)

An AWS Lambda layer that provides GDAL and its Python bindings (`from osgeo import gdal, ogr, osr, gdal_array`).
It targets the Amazon Linux 2023 Python runtimes (python3.12 and later).

It bundles:

| Component | Version | Notes |
|---|---|---|
| GDAL + `osgeo` bindings | 3.13.3 | CLI tools too (`/opt/bin/gdalinfo`, `gdal_translate`, `gdalwarp`, …) |
| PROJ | 9.9.0 | `proj.db` at `/opt/share/proj` |
| GEOS | 3.13 (AL2023 system package) | |
| HDF5 | 1.14.6 | GDAL `HDF5` driver |
| NetCDF-C | 4.9.3 | GDAL `netCDF` driver |
| numpy | 2.x (latest at build time) | optional, needed for `ReadAsArray`/`gdal_array` |

Lambda mounts layers at `/opt`, and everything here is installed under `/opt`, so you **don't need to set any environment variables**.
`/opt/lib` is already on `LD_LIBRARY_PATH` and `/opt/python` is on `sys.path`.
GDAL and PROJ find their data files through the compiled-in `/opt/share/...` paths.

## Build

You need Docker with buildx. Building for arm64 on an x86 host also needs QEMU/binfmt.

```bash
./build.sh                                  # -> dist/gdal-python3.12-x86_64.zip
ARCH=arm64 ./build.sh                       # Graviton
PYTHON_VERSION=3.13 ./build.sh              # other runtime
INCLUDE_NUMPY=false ./build.sh              # if your function ships its own numpy
```

Change component versions with the `ARG`s at the top of the `Dockerfile`.

## Test locally

```bash
./test.sh   # runs tests/handler.py in a clean Lambda image with the layer mounted at /opt
```

## Publish

The zip is larger than 50 MB, so upload it through S3:

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

- If your function also packages numpy, build with `INCLUDE_NUMPY=false`. Your copy then takes precedence, and the bindings were compiled against numpy 2.x, so use a numpy 2.x as well.
- Reading from S3 directly works via `/vsis3/bucket/key` and uses the function's IAM role credentials.
- Write scratch files to `/tmp` (the only writable path).
