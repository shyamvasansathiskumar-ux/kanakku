"""Polite fetching.

One request at a time, at least `min_interval` seconds apart, a descriptive
User-Agent with a contact address, robots.txt respected, and the raw bytes
hashed before anything is parsed, so the archive can always show exactly what
the publisher served.
"""
import time
import urllib.parse
import urllib.request
import urllib.robotparser

from .canon import sha256

USER_AGENT = "Kanakku/0.1 (+https://github.com/shyamvasansathiskumar-ux/kanakku; research archive of public indicators)"


class Fetcher:
    def __init__(self, min_interval=5.0, timeout=30, opener=None):
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0
        self._robots = {}
        self._open = opener or urllib.request.urlopen

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(root)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None  # unreachable robots.txt: treat as no rules
            self._robots[root] = rp
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def get(self, url):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with self._open(req, timeout=self.timeout) as resp:
            body = resp.read()
        self._last = time.monotonic()
        return body, sha256(body)
