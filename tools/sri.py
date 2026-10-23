"""Stamp Subresource Integrity hashes onto the site's scripts and stylesheets.

  python3 tools/sri.py          # rewrite docs/index.html in place
  python3 tools/sri.py --check  # exit 1 if any hash is missing or stale (used by the tests)

If any file is changed after the page is published (on the host, in a cache, in transit),
the browser refuses to run it rather than running something else.
"""
import base64
import hashlib
import os
import re
import sys

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
TAG = re.compile(r'<(script|link)\b([^>]*?)\s(src|href)="([^"]+)"([^>]*)>')


def sri(path):
    with open(os.path.join(DOCS, path), "rb") as f:
        return "sha384-" + base64.b64encode(hashlib.sha384(f.read()).digest()).decode()


INTEGRITY = re.compile(r'\s+integrity="[^"]*"')


def stamp(html):
    def fix(m):
        tag, before, attr, url, after = m.groups()
        if url.startswith(("http:", "https:", "//", "#", "data:")):
            return m.group(0)   # only files served from this site
        if tag == "link" and 'rel="stylesheet"' not in before + after:
            return m.group(0)
        if not os.path.exists(os.path.join(DOCS, url)):
            return m.group(0)
        before, after = INTEGRITY.sub("", before), INTEGRITY.sub("", after)
        return f'<{tag}{before} {attr}="{url}" integrity="{sri(url)}"{after}>'
    return TAG.sub(fix, html)


def main(argv):
    path = os.path.join(DOCS, "index.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    new = stamp(html)
    if "--check" in argv:
        if new != html:
            print("integrity hashes are missing or stale: run python3 tools/sri.py")
            return 1
        print("integrity hashes are current")
        return 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print("stamped", len(re.findall(r'integrity="', new)), "tags")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
