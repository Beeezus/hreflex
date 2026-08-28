"""Targeted correctness cases, several derived from the failure modes the
html5lib-tests tokenizer conformance suite is designed to catch: raw-text
content that must never be scanned for tags, malformed/unterminated tags,
and attribute quoting edge cases.

Runs against both backends (see `extract` fixture below) -- pure Python
and, when built, the Rust/PyO3 native extension. Both must satisfy the
same conformance cases; that's the whole point of porting rather than
re-deriving the algorithm.
"""

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


def links(extract, html_text):
    return list(extract(html_text))


def test_basic_relative_and_absolute(extract):
    html_text = '<a href="/a">A</a><a href="https://other.com/b">B</a>'
    assert links(extract, html_text) == ["/a", "https://other.com/b"]


def test_all_three_quoting_styles(extract):
    html_text = (
        '<a href="/dq">x</a>'
        "<a href='/sq'>x</a>"
        "<a href=/bare>x</a>"
    )
    assert links(extract, html_text) == ["/dq", "/sq", "/bare"]


def test_mixed_case_tag_and_attribute(extract):
    html_text = '<A HrEf="/x">x</A>'
    assert links(extract, html_text) == ["/x"]


def test_entity_decoded_href(extract):
    html_text = '<a href="/search?a=1&amp;b=2">x</a>'
    assert links(extract, html_text) == ["/search?a=1&b=2"]


def test_quoted_gt_inside_attribute_does_not_truncate_tag(extract):
    html_text = '<a title="a > b" href="/x">x</a>'
    assert links(extract, html_text) == ["/x"]


def test_href_inside_script_is_not_extracted(extract):
    html_text = '<script>var s = "<a href=\\"/evil\\">";</script><a href="/real">x</a>'
    assert links(extract, html_text) == ["/real"]


def test_href_inside_style_and_comment_and_title_not_extracted(extract):
    html_text = (
        "<!-- <a href=\"/commented\">x</a> -->"
        '<style>a::before { content: "<a href=\\"/css\\">"; }</style>'
        '<title>&lt;a href="/title"&gt;</title>'
        '<a href="/real">x</a>'
    )
    assert links(extract, html_text) == ["/real"]


def test_unterminated_script_consumes_to_end_of_document(extract):
    html_text = '<script>var x = "<a href=\\"/evil\\">"'
    assert links(extract, html_text) == []


def test_raw_text_tags_do_not_nest(extract):
    # Per WHATWG spec, the first </script> ends the element, full stop.
    html_text = '<script>a</script>b</script><a href="/real">x</a>'
    assert links(extract, html_text) == ["/real"]


def test_base_tag_is_inert_plain_data(extract):
    # <base> is no longer special-cased -- no URL resolution happens here
    # at all, so there is nothing for a <base href> to change. It should
    # be skipped like any other non-<a> tag.
    html_text = '<base href="https://cdn.example.com/assets/"><a href="img.png">x</a>'
    assert links(extract, html_text) == ["img.png"]


def test_illegally_nested_a_tags_do_not_crash(extract):
    html_text = '<a href="/outer"><a href="/inner">x</a></a>'
    assert links(extract, html_text) == ["/outer", "/inner"]


def test_a_tag_without_href_is_skipped(extract):
    html_text = '<a name="anchor">x</a><a href="/real">y</a>'
    assert links(extract, html_text) == ["/real"]


def test_fragment_and_query_preserved(extract):
    html_text = '<a href="/x?a=1#frag">x</a>'
    assert links(extract, html_text) == ["/x?a=1#frag"]


def test_self_closing_anchor(extract):
    html_text = '<a href="/x"/><a href="/y">y</a>'
    assert links(extract, html_text) == ["/x", "/y"]


def test_hyphenated_attribute_ending_in_href_is_not_mistaken_for_href(extract):
    # Regression: `href\s*=` with no boundary guard matched *inside*
    # `data-original-href=`, extracting the wrong value entirely.
    html_text = '<a data-original-href="/wrong" href="/right">x</a>'
    assert links(extract, html_text) == ["/right"]


def test_camelcase_attribute_ending_in_href_is_not_mistaken_for_href(extract):
    html_text = '<a originalHref="/wrong" href="/right">x</a>'
    assert links(extract, html_text) == ["/right"]


def test_href_suffixed_attribute_with_no_real_href_yields_nothing(extract):
    html_text = '<a data-original-href="/wrong">x</a>'
    assert links(extract, html_text) == []
