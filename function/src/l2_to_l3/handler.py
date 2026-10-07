"""Lambda entry point: build an 8-day Gulf of Mexico composite from OB.DAAC L2 swaths.

Event (all keys optional):
    {"date": "2025-06-03"}   composite the 8-day period containing this date;
                             default is the most recent complete period
    {"short_name": "MODISA_L2_OC", "variable": "chlor_a"}   override the defaults

GDAL (osgeo) and numpy come from the GDAL layer (see ../../../layer); don't
package them with the function.
"""
import logging
import os
from datetime import date, datetime, timezone

import boto3

from . import cmr, earthdata, periods
from .composite import Composite, Grid, grid_swath

log = logging.getLogger()
log.setLevel(logging.INFO)

# Gulf of Mexico (west, south, east, north), in degrees.
GULF_OF_MEXICO = (-98.0, 18.0, -80.0, 31.0)


def lambda_handler(event, context):
    event = event or {}
    short_name = event.get("short_name", os.environ.get("SHORT_NAME", "MODISA_L2_OC"))
    variable = event.get("variable", os.environ.get("VARIABLE", "chlor_a"))
    resolution = float(os.environ.get("RESOLUTION_DEG", "0.01"))
    bucket = os.environ["OUTPUT_BUCKET"]
    prefix = os.environ.get("OUTPUT_PREFIX", "l3").strip("/")

    if "date" in event:
        start, end = periods.period_containing(date.fromisoformat(event["date"]))
    else:
        start, end = periods.latest_complete_period(datetime.now(timezone.utc).date())

    urls = cmr.find_granules(short_name, GULF_OF_MEXICO, start, end)
    log.info("%s %s..%s: %d granules", short_name, start, end, len(urls))

    s3 = earthdata.s3_client(os.environ["EDL_SECRET_ID"])
    composite = Composite(Grid(GULF_OF_MEXICO, resolution))
    for url in urls:
        src_bucket, key = url.removeprefix("s3://").split("/", 1)
        local = f"/tmp/{os.path.basename(key)}"
        s3.download_file(src_bucket, key, local)
        try:
            composite.add(grid_swath(local, variable, composite.grid))
        except Exception:
            log.exception("Skipping %s", url)
        finally:
            os.remove(local)

    if composite.granules == 0:
        log.warning("No valid %s data for %s..%s", variable, start, end)
        return {"start": start.isoformat(), "end": end.isoformat(), "granules": len(urls), "used": 0, "output": None}

    name = f"{short_name}.{start:%Y%m%d}_{end:%Y%m%d}.L3m.8D.{variable}.GoM.tif"
    out_key = f"{prefix}/{short_name}/{variable}/{start:%Y}/{name}"
    local_out = f"/tmp/{name}"
    composite.write(local_out, variable)
    boto3.client("s3").upload_file(local_out, bucket, out_key)
    os.remove(local_out)

    output = f"s3://{bucket}/{out_key}"
    log.info("Wrote %s from %d of %d granules", output, composite.granules, len(urls))
    return {"start": start.isoformat(), "end": end.isoformat(), "granules": len(urls),
            "used": composite.granules, "output": output}
