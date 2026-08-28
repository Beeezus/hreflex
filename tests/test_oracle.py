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

import pytest
from selectolax.parser import HTMLParser

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


def _oracle_links(html_text):
    return [
        node.attributes["href"]
        for node in HTMLParser(html_text).css("a[href]")
        if node.attributes.get("href")
    ]


@pytest.mark.parametrize(
    "filename",
    ["hackernews.html", "midnightlabs.html", "wikipedia.html"],
)
def test_matches_selectolax_on_real_page(extract, filename):
    html_text = (FIXTURES / filename).read_text(encoding="utf-8")
    assert list(extract(html_text)) == _oracle_links(html_text)
