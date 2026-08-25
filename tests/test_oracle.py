"""Cross-validate against selectolax (a real, spec-conformant HTML5 parser)
on real-world pages. Disagreements are either a hreflex bug or a genuine
edge case worth a named test in test_conformance.py -- this catches real
bugs far faster than hand-enumerating every case.
"""

from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

from hreflex import extract_links

FIXTURES = Path(__file__).parent / "fixtures"


def _oracle_links(html_text, base_url):
    from urllib.parse import urljoin

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
def test_matches_selectolax_on_real_page(filename, base_url):
    html_text = (FIXTURES / filename).read_text(encoding="utf-8")
    ours = list(extract_links(html_text, base_url))
    oracle = _oracle_links(html_text, base_url)
    assert ours == oracle
