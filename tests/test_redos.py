"""Every quantifier in the tokenizer's patterns is over a single,
non-overlapping character class by construction (no `(a+)+`-style nested
quantifiers), so runtime should stay near-linear even on adversarial input.
These are hard timeout assertions, not micro-benchmarks: a regression into
catastrophic backtracking should fail the test suite, not just show up as
"a bit slower" in a benchmark someone has to notice.
"""

import time

from hreflex import extract_links


def _timed(html_text, base_url="https://example.com/"):
    start = time.perf_counter()
    list(extract_links(html_text, base_url))
    return time.perf_counter() - start


def test_many_unclosed_angle_brackets():
    html_text = "<a " * 200_000
    assert _timed(html_text) < 2.0


def test_long_unterminated_quote():
    html_text = '<a href="' + ("x" * 2_000_000)
    assert _timed(html_text) < 2.0


def test_many_bare_lt_a_without_gt():
    html_text = "<a" * 500_000
    assert _timed(html_text) < 2.0


def test_runtime_scales_roughly_linearly():
    small = "<a href=\"/x\">x</a>" * 10_000
    large = "<a href=\"/x\">x</a>" * 100_000
    t_small = _timed(small)
    t_large = _timed(large)
    # Allow generous slack (constant factors, GC, scheduling noise) --
    # this only needs to catch a genuine superlinear blowup, e.g. >20x
    # runtime for 10x input, not assert a tight ratio.
    assert t_large < t_small * 20 + 0.5
