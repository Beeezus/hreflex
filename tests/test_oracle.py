"""Cross-validate against selectolax (a real, spec-conformant HTML5 parser)
on real-world pages. Disagreements are either a hreflex bug or a genuine
edge case worth a named test in test_conformance.py -- this catches real
bugs far faster than hand-enumerating every case. (It's how the
data-original-href boundary-guard bug was actually found -- not by a
hand-written case, but by adding wikipedia.html to this fixture set.)

Runs against both backends -- see test_conformance.py for the `extract`
fixture.
"""

from pathlib import Path
from urllib.parse import urljoin

import pytest
from selectolax.parser import HTMLParser

from _url_compare import normalize
from hreflex import extract_links as extract_pure

try:
    from hreflex.native import extract_links as extract_native
except ImportError:
    extract_native = None

_BACKENDS = [extract_pure] + ([extract_native] if extract_native else [])
_BACKEND_IDS = ["pure"] + (["native"] if extract_native else [])

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(params=_BACKENDS, ids=_BACKEND_IDS)
def extract(request):
    return request.param


def _oracle_links(html_text, base_url):
    links = []
    for node in HTMLParser(html_text).css("a[href]"):
        href = node.attributes.get("href")
        if href:
            links.append(urljoin(base_url, href))
    return links


@pytest.mark.parametrize(
    "filename,base_url",
    [
        ("hackernews.html", "https://news.ycombinator.com/"),
        ("midnightlabs.html", "https://www.midnightlabs.ai/"),
        # This page has both `data-mw-original-href` and other href-suffixed
        # attribute names -- the fixture that would have caught the
        # boundary-guard bug in _HREF_RE if it had been here from the start.
        ("wikipedia.html", "https://en.wikipedia.org/wiki/Web_scraping"),
    ],
)
def test_matches_selectolax_on_real_page(extract, filename, base_url):
    html_text = (FIXTURES / filename).read_text(encoding="utf-8")
    ours = [normalize(u) for u in extract(html_text, base_url)]
    oracle = [normalize(u) for u in _oracle_links(html_text, base_url)]
    assert ours == oracle
