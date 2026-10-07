# L2 to L3 on AWS Lambda

A Python Lambda function that processes Level-2 data into Level-3 products, plus the GDAL layer it runs on.

| Folder | What it is | How often it changes |
|---|---|---|
| [`layer/`](layer/) | Lambda layer with GDAL, PROJ, GEOS, HDF5, NetCDF and numpy, built from source with Docker | Rarely. The build is slow. |
| [`function/`](function/) | The L2 → L3 processing code (`l2_to_l3` package) | Often. Deploys are fast. |

The two live in one repo because the function only works with this exact layer: python3.12, x86_64, with numpy and GDAL coming from the layer.
Change them together in one commit when they need to move together, and otherwise build and deploy each on its own.

## Conventions

- **No build output in git.** `dist/` and zips are ignored. `layer/Dockerfile` is the source of truth, and built layer zips live in S3.
- **Every component in the layer is pinned** in `layer/Dockerfile` (GDAL, PROJ, HDF5, NetCDF, numpy), so two builds from the same commit match.
- **Tag layer releases** after publishing, e.g. `layer-v1`, with the GDAL version and the resulting `LayerVersionArn` in the tag message.
- **The function doesn't package numpy or gdal.** They come from the layer, so `function/requirements.txt` must not list them.

See [`layer/README.md`](layer/README.md) to build, test and publish the layer.
