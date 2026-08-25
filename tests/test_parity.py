"""The pure-Python implementation and the Rust/PyO3 port are supposed to
be the same algorithm in two languages. If they ever disagree on real
input, that's a bug in one of them -- this is a correctness resource in
its own right, independent of test_conformance.py/test_oracle.py.
"""

from pathlib import Path

import pytest

from _url_compare import normalize
from hreflex import extract_links as extract_pure

try:
    from hreflex.native import extract_links as extract_native
except ImportError:
    extract_native = None

pytestmark = pytest.mark.skipif(
    extract_native is None, reason="hreflex.native not built (maturin develop)"
)

FIXTURES = Path(__file__).parent / "fixtures"

_ADVERSARIAL_CASES = [
    '<a href="/a">A</a><a href="https://other.com/b">B</a>',
    '<A HrEf="/x">x</A>',
    '<a href="/search?a=1&amp;b=2">x</a>',
    '<title>&lt;a href="/title"&gt;</title><a href="/real">x</a>',
    '<script>var s = "<a href=\\"/evil\\">";</script><a href="/real">x</a>',
    '<base href="https://cdn.example.com/assets/"><a href="img.png">x</a>',
    '<a data-original-href="/wrong" href="/right">x</a>',
    '<a href="/x"/><a href="/y">y</a>',
    "<a " * 1_000,
]


@pytest.mark.parametrize("html_text", _ADVERSARIAL_CASES)
def test_backends_agree_on_adversarial_cases(html_text):
    base_url = "https://example.com/"
    pure = [normalize(u) for u in extract_pure(html_text, base_url)]
    native = [normalize(u) for u in extract_native(html_text, base_url)]
    assert pure == native


@pytest.mark.parametrize(
    "filename,base_url",
    [
        ("hackernews.html", "https://news.ycombinator.com/"),
        ("midnightlabs.html", "https://www.midnightlabs.ai/"),
        ("wikipedia.html", "https://en.wikipedia.org/wiki/Web_scraping"),
    ],
)
def test_backends_agree_on_real_pages(filename, base_url):
    html_text = (FIXTURES / filename).read_text(encoding="utf-8")
    pure = [normalize(u) for u in extract_pure(html_text, base_url)]
    native = [normalize(u) for u in extract_native(html_text, base_url)]
    assert pure == native
