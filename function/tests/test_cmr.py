import io
import json
import unittest
from datetime import date
from unittest import mock

from l2_to_l3 import cmr


def item(name):
    return {"umm": {"RelatedUrls": [
        {"Type": "GET DATA", "URL": f"https://obdaac-tea.earthdatacloud.nasa.gov/ob-cumulus-prod-public/{name}"},
        {"Type": "GET DATA VIA DIRECT ACCESS", "URL": f"s3://ob-cumulus-prod-public/{name}"},
    ]}}


class FakeResponse(io.BytesIO):
    def __init__(self, items, search_after=None):
        super().__init__(json.dumps({"items": items}).encode())
        self.headers = {"CMR-Search-After": search_after} if search_after else {}


class CmrTests(unittest.TestCase):
    def test_dedupes_and_pages(self):
        pages = [
            FakeResponse([item("B.nc"), item("A.nc"), item("A.nc")], search_after="x"),
            FakeResponse([item("C.nc"), {"umm": {}}], search_after="y"),
            FakeResponse([]),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=pages) as urlopen:
            urls = cmr.find_granules("MODISA_L2_OC", (-98, 18, -80, 31), date(2025, 6, 2), date(2025, 6, 9))
        self.assertEqual(urls, [f"s3://ob-cumulus-prod-public/{n}.nc" for n in "ABC"])
        query = urlopen.call_args_list[0].args[0].full_url
        self.assertIn("bounding_box=-98%2C18%2C-80%2C31", query)
        self.assertIn("temporal=2025-06-02T00%3A00%3A00Z%2C2025-06-09T23%3A59%3A59Z", query)
        self.assertEqual(urlopen.call_args_list[1].args[0].get_header("Cmr-search-after"), "x")
