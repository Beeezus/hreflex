"""Normalizes away two known, spec-level (not bug-level) differences
between the pure-Python backend's URL joining (`urllib.parse.urljoin`,
RFC 3986) and the native backend's (`url` crate, WHATWG URL Standard):
WHATWG mandates a '/' path on an authority-only URL where RFC 3986
leaves it absent, and WHATWG round-trips a bare empty fragment ('#')
where urllib drops it. Confirmed to be the *only* divergence across every
real-page fixture (test_parity.py) -- everything else is byte-identical.
"""

from urllib.parse import urlsplit


def normalize(url: str) -> tuple:
    scheme, netloc, path, query, fragment = urlsplit(url)
    if path in ("", "/"):
        path = ""
    return (scheme, netloc, path, query, fragment)
