"""Runs lambda_handler end to end with CMR, Earthdata and S3 mocked out."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np
from osgeo import gdal

from l2_to_l3 import handler
from test_composite import write_l2


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        write_l2(os.path.join(self.tmp, "A.nc"), np.full((10, 10), 2.0), np.zeros((10, 10)))
        self.uploaded = {}

    def download(self, bucket, key, local):
        self.assertEqual(bucket, "ob-cumulus-prod-public")
        shutil.copy(os.path.join(self.tmp, key), local)

    def upload(self, local, bucket, key):
        ds = gdal.Open(local)
        self.uploaded[f"s3://{bucket}/{key}"] = ds.GetRasterBand(1).ReadAsArray()

    def test_composites_period_and_uploads(self):
        source = mock.Mock(download_file=self.download)
        dest = mock.Mock(upload_file=self.upload)
        with mock.patch.dict(os.environ, {"OUTPUT_BUCKET": "out", "EDL_SECRET_ID": "edl", "RESOLUTION_DEG": "0.1"}), \
             mock.patch.object(handler.cmr, "find_granules", return_value=["s3://ob-cumulus-prod-public/A.nc"]) as find, \
             mock.patch.object(handler.earthdata, "s3_client", return_value=source), \
             mock.patch.object(handler.boto3, "client", return_value=dest):
            result = handler.lambda_handler({"date": "2025-06-03"}, None)

        find.assert_called_once()
        out = "s3://out/l3/MODISA_L2_OC/chlor_a/2025/MODISA_L2_OC.20250602_20250609.L3m.8D.chlor_a.GoM.tif"
        self.assertEqual(result, {"start": "2025-06-02", "end": "2025-06-09", "granules": 1, "used": 1, "output": out})
        self.assertEqual(np.nanmax(self.uploaded[out]), 2.0)
        self.assertFalse(os.path.exists("/tmp/A.nc"))
