"""Smoke test: exercises GDAL, OGR, OSR/PROJ, GEOS, NetCDF/HDF5 and gdal_array."""
import numpy as np
from osgeo import gdal, ogr, osr, gdal_array

gdal.UseExceptions()


def handler(event=None, context=None):
    # Raster round trip through an in-memory NetCDF file (exercises netCDF + HDF5).
    arr = np.arange(100, dtype="float32").reshape(10, 10)
    mem = gdal_array.OpenArray(arr)
    mem.SetGeoTransform([-10, 2, 0, 50, 0, -2])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    mem.SetSpatialRef(srs)
    gdal.Translate("/tmp/test.nc", mem, format="netCDF", creationOptions=["FORMAT=NC4"])
    back = gdal.Open("/tmp/test.nc").ReadAsArray()
    assert np.array_equal(arr, back)

    # Reprojection (exercises PROJ + proj.db).
    warped = gdal.Warp("", mem, format="MEM", dstSRS="EPSG:3857")

    # Geometry ops (exercises GEOS).
    buf = ogr.CreateGeometryFromWkt("POINT (0 0)").Buffer(1)

    result = {
        "gdal": gdal.__version__,
        "proj": ".".join(map(str, (osr.GetPROJVersionMajor(), osr.GetPROJVersionMinor(), osr.GetPROJVersionMicro()))),
        "has_geos": ogr.GetGEOSVersionMajor() > 0,
        "drivers": gdal.GetDriverCount(),
        "netcdf": gdal.GetDriverByName("netCDF") is not None,
        "hdf5": gdal.GetDriverByName("HDF5") is not None,
        "warped_size": [warped.RasterXSize, warped.RasterYSize],
        "buffer_area": round(buf.Area(), 3),
    }
    print(result)
    return result


if __name__ == "__main__":
    handler()
