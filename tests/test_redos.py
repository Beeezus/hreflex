"""Every quantifier/search primitive in both backends advances the scan
position monotonically by construction (no rescanning, no backtracking
over the whole document) -- these are hard timeout assertions on
adversarial input, not micro-benchmarks. A regression into quadratic
behavior, in either backend, should fail the test suite outright, the way
the pure-Python version's first (rejected) design actually did: measured
0.08s / 2.1s / 8.6s for 1k / 5k / 10k chars before the fix.

Runs against both backends -- see test_conformance.py for the `extract`
fixture.
"""

import time

import pytest

from hreflex import extract_links as extract_pure

try:
    from hreflex.native import extract_links as extract_native
except ImportError:
    extract_native = None

_BACKENDS = [extract_pure] + ([extract_native] if extract_native else [])
_BACKEND_IDS = ["pure"] + (["native"] if extract_native else [])


@pytest.fixture(params=_BACKENDS, ids=_BACKEND_IDS)
def extract(request):
    return request.param


def _timed(extract, html_text):
    start = time.perf_counter()
    list(extract(html_text))
    return time.perf_counter() - start


def test_many_unclosed_angle_brackets(extract):
    html_text = "<a " * 200_000
    assert _timed(extract, html_text) < 2.0


def test_long_unterminated_quote(extract):
    html_text = '<a href="' + ("x" * 2_000_000)
    assert _timed(extract, html_text) < 2.0


def test_many_bare_lt_a_without_gt(extract):
    html_text = "<a" * 500_000
    assert _timed(extract, html_text) < 2.0


def test_runtime_scales_roughly_linearly(extract):
    small = "<a href=\"/x\">x</a>" * 10_000
    large = "<a href=\"/x\">x</a>" * 100_000
    t_small = _timed(extract, small)
    t_large = _timed(extract, large)
    # Allow generous slack (constant factors, GC, scheduling noise) --
    # this only needs to catch a genuine superlinear blowup, e.g. >20x
    # runtime for 10x input, not assert a tight ratio.
    assert t_large < t_small * 20 + 0.5
