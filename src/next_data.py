"""Fetches a FotMob page's embedded __NEXT_DATA__ JSON.

Tries a plain requests.get first (no browser, ~0.5s per page). If that fails
or the page comes back without __NEXT_DATA__ (e.g. bot protection), falls
back to loading the page in the Selenium driver.
"""

import json
import re
import requests
from selenium.common.exceptions import TimeoutException, WebDriverException
from . import league_scraper

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Referer": "https://www.fotmob.com/",
})

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def fetch_page_props(url, driver=None):
    """
    Returns props.pageProps for a FotMob page, or {} if it can't be read.

    Args:
        url (str): Full FotMob URL
        driver: Optional WebDriver used as a fallback when requests fails

    Raises:
        TimeoutException / WebDriverException from the driver fallback, so
        callers can recover the driver (same convention as the other scrapers).
    """
    try:
        resp = _SESSION.get(url, timeout=20)
        match = _NEXT_DATA_RE.search(resp.text)
        if resp.ok and match:
            return json.loads(match.group(1)).get("props", {}).get("pageProps", {})
        print(f"requests got no __NEXT_DATA__ for {url} (HTTP {resp.status_code})")
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"requests failed for {url}: {e}")

    if driver is None:
        return {}

    try:
        driver.get(url)
    except (TimeoutException, WebDriverException):
        raise

    next_data = league_scraper._extract_next_data(driver)
    return (next_data or {}).get("props", {}).get("pageProps", {})
