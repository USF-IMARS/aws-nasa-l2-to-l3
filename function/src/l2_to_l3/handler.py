"""Lambda entry point for the L2 -> L3 processing function.

GDAL (osgeo) and numpy come from the GDAL layer (see ../../../layer); don't
package them with the function.
"""
from osgeo import gdal

gdal.UseExceptions()


def lambda_handler(event, context):
    raise NotImplementedError("L2 -> L3 processing not written yet")
