"""Grid OB.DAAC Level-2 swaths onto a regular lat/lon grid and average them.

Each L2 file is a satellite swath: the variable is a 2-D array in scan
geometry, with per-pixel latitude/longitude in navigation_data. GDAL warps
each swath onto the output grid using those arrays (its GEOLOC_ARRAY
transformer). The gridded swaths are then averaged pixel by pixel.
"""
import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()
# GDAL's geolocation transformer writes temporary files, and only /tmp is
# writable in Lambda (the default is the read-only working directory).
gdal.SetConfigOption("CPL_TMPDIR", "/tmp")

# Pixels with any of these l2_flags set are dropped. This is OB.DAAC's
# default exclusion list for its standard L3 chlorophyll products.
DEFAULT_FLAGS = (
    "ATMFAIL", "LAND", "HILT", "HISATZEN", "STRAYLIGHT", "CLDICE", "COCCOLITH",
    "LOWLW", "CHLWARN", "CHLFAIL", "NAVWARN", "MAXAERITER", "ATMWARN",
    "HISOLZEN", "NAVFAIL", "FILTER", "HIGLINT",
)
NODATA = -32767.0


class Grid:
    """A regular EPSG:4326 grid covering bbox (west, south, east, north)."""

    def __init__(self, bbox: tuple[float, float, float, float], resolution: float):
        self.bbox = bbox
        self.resolution = resolution
        west, south, east, north = bbox
        self.width = round((east - west) / resolution)
        self.height = round((north - south) / resolution)
        self.geotransform = (west, resolution, 0.0, north, 0.0, -resolution)


class Composite:
    """Running per-pixel sum and count of valid values on a Grid."""

    def __init__(self, grid: Grid):
        self.grid = grid
        self.sum = np.zeros((grid.height, grid.width), dtype="float64")
        self.count = np.zeros((grid.height, grid.width), dtype="uint16")
        self.granules = 0

    def add(self, gridded: np.ndarray) -> None:
        valid = ~np.isnan(gridded)
        if valid.any():
            self.sum[valid] += gridded[valid]
            self.count[valid] += 1
            self.granules += 1

    def write(self, path: str, description: str) -> None:
        """Write a 2-band Cloud-Optimized GeoTIFF: band 1 the mean, band 2 the
        number of swaths contributing to each pixel."""
        mean = np.full(self.sum.shape, np.nan, dtype="float32")
        np.divide(self.sum, self.count, out=mean, where=self.count > 0, casting="unsafe")

        mem = gdal.GetDriverByName("MEM").Create("", self.grid.width, self.grid.height, 2, gdal.GDT_Float32)
        mem.SetGeoTransform(self.grid.geotransform)
        mem.SetSpatialRef(_wgs84())
        mem.SetMetadataItem("GRANULE_COUNT", str(self.granules))
        for i, (data, name) in enumerate(((mean, description), (self.count.astype("float32"), "count")), 1):
            band = mem.GetRasterBand(i)
            band.WriteArray(data)
            band.SetNoDataValue(float("nan"))
            band.SetDescription(name)
        gdal.Translate(path, mem, format="COG", creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=YES"])


def grid_swath(nc_path: str, variable: str, grid: Grid,
               exclude_flags: tuple[str, ...] = DEFAULT_FLAGS) -> np.ndarray:
    """Warp one L2 swath's `variable` onto `grid`. Returns a float32 array with
    NaN where there is no valid data."""
    values = _read_masked(nc_path, variable, exclude_flags)

    src = gdal.GetDriverByName("MEM").Create("", values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
    src.GetRasterBand(1).WriteArray(values)
    src.GetRasterBand(1).SetNoDataValue(NODATA)
    src.SetMetadata({
        "SRS": _wgs84().ExportToWkt(),
        "X_DATASET": f'NETCDF:"{nc_path}":/navigation_data/longitude', "X_BAND": "1",
        "Y_DATASET": f'NETCDF:"{nc_path}":/navigation_data/latitude', "Y_BAND": "1",
        "PIXEL_OFFSET": "0", "LINE_OFFSET": "0", "PIXEL_STEP": "1", "LINE_STEP": "1",
        # L2 latitude/longitude give pixel centres; GDAL otherwise assumes corners.
        "GEOREFERENCING_CONVENTION": "PIXEL_CENTER",
    }, "GEOLOCATION")

    gridded = np.full((grid.height, grid.width), np.nan, dtype="float32")
    window = _swath_window(nc_path, grid)
    if window is None:
        return gridded

    # Warp onto just the part of the grid the swath covers. Warping onto the
    # whole grid would be slower, and GDAL can miss (and skip) a swath that
    # covers only a small part of a large output.
    row0, row1, col0, col1 = window
    west, _, _, north = grid.bbox
    res = grid.resolution
    out = gdal.Warp(
        "", src, format="MEM",
        outputBounds=(west + col0 * res, north - row1 * res, west + col1 * res, north - row0 * res),
        width=col1 - col0, height=row1 - row0,
        dstSRS="EPSG:4326", resampleAlg="near",
        srcNodata=NODATA, dstNodata=float("nan"), outputType=gdal.GDT_Float32,
        transformerOptions=["METHOD=GEOLOC_ARRAY"],
    )
    gridded[row0:row1, col0:col1] = out.GetRasterBand(1).ReadAsArray()
    return gridded


def _swath_window(nc_path: str, grid: Grid) -> tuple[int, int, int, int] | None:
    """Return the (row0, row1, col0, col1) slice of `grid` that the swath's
    valid lat/lon covers, padded by one cell, or None if they don't overlap."""
    lon = gdal.Open(f'NETCDF:"{nc_path}":/navigation_data/longitude').ReadAsArray()
    lat = gdal.Open(f'NETCDF:"{nc_path}":/navigation_data/latitude').ReadAsArray()
    ok = (np.abs(lon) <= 180) & (np.abs(lat) <= 90)  # navigation fill is -999
    if not ok.any():
        return None
    west, _, _, north = grid.bbox
    col0 = max(int(np.floor((lon[ok].min() - west) / grid.resolution)) - 1, 0)
    col1 = min(int(np.ceil((lon[ok].max() - west) / grid.resolution)) + 1, grid.width)
    row0 = max(int(np.floor((north - lat[ok].max()) / grid.resolution)) - 1, 0)
    row1 = min(int(np.ceil((north - lat[ok].min()) / grid.resolution)) + 1, grid.height)
    if col0 >= col1 or row0 >= row1:
        return None
    return row0, row1, col0, col1


def _read_masked(nc_path: str, variable: str, exclude_flags: tuple[str, ...]) -> np.ndarray:
    """Read `variable` with scale/offset applied, setting fill values, out of
    range values and flagged pixels to NODATA."""
    ds = gdal.Open(f'NETCDF:"{nc_path}":/geophysical_data/{variable}')
    band = ds.GetRasterBand(1)
    raw = band.ReadAsArray()
    values = raw * (band.GetScale() or 1.0) + (band.GetOffset() or 0.0)
    bad = np.zeros(raw.shape, dtype=bool)
    if band.GetNoDataValue() is not None:
        bad |= raw == band.GetNoDataValue()
    md = band.GetMetadata()
    if "valid_min" in md:
        bad |= values < float(md["valid_min"])
    if "valid_max" in md:
        bad |= values > float(md["valid_max"])

    flags_ds = gdal.Open(f'NETCDF:"{nc_path}":/geophysical_data/l2_flags')
    flags = flags_ds.GetRasterBand(1).ReadAsArray().astype("int64") & 0xFFFFFFFF
    bad |= (flags & flag_bits(flags_ds.GetRasterBand(1).GetMetadata(), exclude_flags)) != 0

    values = values.astype("float32")
    values[bad] = NODATA
    return values


def flag_bits(l2_flags_metadata: dict, names: tuple[str, ...]) -> int:
    """Combine the bit masks of the named flags, using l2_flags' CF
    flag_meanings/flag_masks attributes as GDAL reports them."""
    meanings = l2_flags_metadata["flag_meanings"].split()
    masks = [int(m) & 0xFFFFFFFF for m in l2_flags_metadata["flag_masks"].strip("{}").split(",")]
    lookup = dict(zip(meanings, masks))
    bits = 0
    for name in names:
        bits |= lookup.get(name, 0)
    return bits


def _wgs84() -> osr.SpatialReference:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs
