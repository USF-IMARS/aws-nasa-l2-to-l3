"""Temporary S3 credentials for OB.DAAC's Earthdata Cloud bucket.

Reading s3://ob-cumulus-prod-public requires short-lived AWS credentials issued
by the DAAC's credentials endpoint after an Earthdata Login (EDL). They expire
after one hour and only work from us-west-2.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar

import boto3

S3_CREDENTIALS_URL = "https://obdaac-tea.earthdatacloud.nasa.gov/s3credentials"
EDL_HOST = "urs.earthdata.nasa.gov"

_cached: dict | None = None


def s3_client(edl_secret_id: str):
    """Return a boto3 S3 client authorized for OB.DAAC, reusing credentials
    across warm invocations until they are 5 minutes from expiring."""
    global _cached
    if _cached is None or _cached["expires"] - datetime.now(timezone.utc) < timedelta(minutes=5):
        creds = fetch_credentials(*edl_login(edl_secret_id))
        _cached = {
            "client": boto3.client(
                "s3",
                region_name="us-west-2",
                aws_access_key_id=creds["accessKeyId"],
                aws_secret_access_key=creds["secretAccessKey"],
                aws_session_token=creds["sessionToken"],
            ),
            "expires": datetime.fromisoformat(creds["expiration"]),
        }
    return _cached["client"]


def edl_login(secret_id: str) -> tuple[str, str]:
    """Read the EDL username/password from a Secrets Manager secret holding
    {"username": ..., "password": ...}."""
    secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
    value = json.loads(secret["SecretString"])
    return value["username"], value["password"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_credentials(username: str, password: str) -> dict:
    """Follow the endpoint's EDL OAuth redirects manually, sending the EDL
    password only to the EDL host, and return the credentials JSON."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(CookieJar()))
    basic = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    url = S3_CREDENTIALS_URL
    for _ in range(10):
        req = urllib.request.Request(url)
        if urllib.parse.urlsplit(url).hostname == EDL_HOST:
            req.add_header("Authorization", basic)
        try:
            with opener.open(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
            url = urllib.parse.urljoin(url, e.headers["Location"])
    raise RuntimeError("Too many redirects fetching OB.DAAC S3 credentials")
