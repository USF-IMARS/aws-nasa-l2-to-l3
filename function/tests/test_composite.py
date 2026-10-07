"""Runs real GDAL against synthetic swaths shaped like OB.DAAC L2 OC files."""
import os
import tempfile
import unittest

import numpy as np
from osgeo import gdal

from l2_to_l3.composite import Composite, Grid, grid_swath

gdal.UseExceptions()

FLAG_NAMES = ["ATMFAIL", "LAND", "PRODWARN", "HIGLINT"]  # bits 0..3
GRID = Grid((-98.0, 18.0, -80.0, 31.0), 0.1)


def write_l2(path, chl, flags, lon0=-94.95, lat0=27.95, step=0.1):
    """Write a grouped netCDF4 like an L2 file: a north-up swath of
    chl.shape pixels whose upper-left pixel centre is at (lon0, lat0). The
    defaults line swath pixel centres up with GRID cell centres."""
    rows, cols = chl.shape
    lat, lon = np.meshgrid(lat0 - step * np.arange(rows), lon0 + step * np.arange(cols), indexing="ij")
    ds = gdal.GetDriverByName("netCDF").CreateMultiDimensional(path)
    root = ds.GetRootGroup()
    dims = [root.CreateDimension("number_of_lines", None, None, rows),
            root.CreateDimension("pixels_per_line", None, None, cols)]

    def var(group, name, data, dtype, attrs):
        arr = group.CreateMDArray(name, dims, gdal.ExtendedDataType.Create(dtype))
        for k, v in attrs.items():
            if isinstance(v, str):
                a = arr.CreateAttribute(k, [], gdal.ExtendedDataType.CreateString())
            else:
                v = np.atleast_1d(v)
                a = arr.CreateAttribute(k, [len(v)] if len(v) > 1 else [], gdal.ExtendedDataType.Create(dtype))
                v = v.tolist() if len(v) > 1 else v.item()
            a.Write(v)
        arr.Write(data)

    nav, geo = root.CreateGroup("navigation_data"), root.CreateGroup("geophysical_data")
    var(nav, "longitude", lon.astype("float32"), gdal.GDT_Float32, {})
    var(nav, "latitude", lat.astype("float32"), gdal.GDT_Float32, {})
    var(geo, "chlor_a", chl.astype("float32"), gdal.GDT_Float32,
        {"_FillValue": np.float32(-32767), "valid_min": np.float32(0.001), "valid_max": np.float32(100)})
    var(geo, "l2_flags", flags.astype("int32"), gdal.GDT_Int32,
        {"flag_masks": np.array([1, 2, 4, 8], dtype="int32"), "flag_meanings": " ".join(FLAG_NAMES)})
    del ds


def pixel(gridded, lon, lat):
    col = int((lon - GRID.bbox[0]) / GRID.resolution)
    row = int((GRID.bbox[3] - lat) / GRID.resolution)
    return gridded[row, col]


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_grid_swath_places_values_and_masks_flags(self):
        chl = np.full((20, 30), 1.0)
        chl[0, 0] = 5.0                # upper-left pixel, centred at (-94.95, 27.95)
        chl[10, 10] = -32767           # fill value
        chl[10, 20] = 500.0            # above valid_max
        flags = np.zeros((20, 30))
        flags[5, 5] = 2                # LAND: excluded by default
        flags[5, 6] = 4                # PRODWARN: not in the exclusion list
        write_l2(self.path("a.nc"), chl, flags)

        out = grid_swath(self.path("a.nc"), "chlor_a", GRID)
        self.assertEqual(out.shape, (130, 180))
        self.assertAlmostEqual(pixel(out, -94.95, 27.95), 5.0)
        self.assertAlmostEqual(pixel(out, -94.05, 26.95), 1.0)
        self.assertTrue(np.isnan(pixel(out, -93.95, 26.95)))   # fill
        self.assertTrue(np.isnan(pixel(out, -92.95, 26.95)))   # out of range
        self.assertTrue(np.isnan(pixel(out, -94.45, 27.45)))   # LAND
        self.assertAlmostEqual(pixel(out, -94.35, 27.45), 1.0)  # PRODWARN kept
        self.assertTrue(np.isnan(pixel(out, -85.0, 25.0)))     # outside the swath

    def test_composite_averages_overlapping_swaths(self):
        write_l2(self.path("a.nc"), np.full((10, 10), 1.0), np.zeros((10, 10)))
        write_l2(self.path("b.nc"), np.full((10, 10), 3.0), np.zeros((10, 10)), lon0=-94.45)
        write_l2(self.path("c.nc"), np.full((10, 10), 2.0), np.full((10, 10), 1))  # all ATMFAIL

        comp = Composite(GRID)
        for name in ("a.nc", "b.nc", "c.nc"):
            comp.add(grid_swath(self.path(name), "chlor_a", GRID))
        self.assertEqual(comp.granules, 2)

        out_path = self.path("out.tif")
        comp.write(out_path, "chlor_a")
        ds = gdal.Open(out_path)
        self.assertEqual(ds.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE"), "COG")
        self.assertEqual(ds.GetGeoTransform(), GRID.geotransform)
        mean, count = ds.GetRasterBand(1).ReadAsArray(), ds.GetRasterBand(2).ReadAsArray()
        self.assertAlmostEqual(pixel(mean, -94.95, 27.95), 1.0)   # only a
        self.assertAlmostEqual(pixel(mean, -94.25, 27.95), 2.0)   # a and b overlap
        self.assertEqual(pixel(count, -94.25, 27.95), 2)
        self.assertAlmostEqual(pixel(mean, -93.65, 27.95), 3.0)   # only b
        self.assertTrue(np.isnan(pixel(mean, -85.0, 25.0)))
