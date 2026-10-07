"""Find OB.DAAC granules in NASA's Common Metadata Repository (CMR).

The ob-cumulus-prod-public bucket is flat (every file sits at the bucket root)
and isn't meant to be listed, so CMR is how granules are found by time and area.
"""
import json
import urllib.parse
import urllib.request
from datetime import date

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
PROVIDER = "OB_CLOUD"


def find_granules(short_name: str, bbox: tuple[float, float, float, float],
                  start: date, end: date) -> list[str]:
    """Return the sorted, de-duplicated s3:// URLs of granules intersecting `bbox`
    (west, south, east, north) between `start` and `end`, inclusive."""
    params = urllib.parse.urlencode({
        "short_name": short_name,
        "provider": PROVIDER,
        "bounding_box": ",".join(map(str, bbox)),
        "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
        "page_size": 2000,
    })
    urls, search_after = set(), None
    while True:
        req = urllib.request.Request(f"{CMR_GRANULES}?{params}")
        if search_after:
            req.add_header("CMR-Search-After", search_after)
        with urllib.request.urlopen(req, timeout=60) as resp:
            search_after = resp.headers.get("CMR-Search-After")
            items = json.load(resp)["items"]
        urls.update(s3_url(item) for item in items)
        if not items or not search_after:
            break
    # CMR lists each OB.DAAC file under two granule records, hence the set.
    urls.discard(None)
    return sorted(urls)


def s3_url(item: dict) -> str | None:
    for link in item["umm"].get("RelatedUrls", []):
        if link.get("Type") == "GET DATA VIA DIRECT ACCESS" and link["URL"].startswith("s3://"):
            return link["URL"]
    return None
