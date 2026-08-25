"""Targeted correctness cases, several derived from the failure modes the
html5lib-tests tokenizer conformance suite is designed to catch: raw-text
content that must never be scanned for tags, malformed/unterminated tags,
and attribute quoting edge cases.
"""

from hreflex import extract_links


def links(html_text, base_url="https://example.com/"):
    return list(extract_links(html_text, base_url))


def test_basic_relative_and_absolute():
    html_text = '<a href="/a">A</a><a href="https://other.com/b">B</a>'
    assert links(html_text) == ["https://example.com/a", "https://other.com/b"]


def test_all_three_quoting_styles():
    html_text = (
        '<a href="/dq">x</a>'
        "<a href='/sq'>x</a>"
        "<a href=/bare>x</a>"
    )
    assert links(html_text) == [
        "https://example.com/dq",
        "https://example.com/sq",
        "https://example.com/bare",
    ]


def test_mixed_case_tag_and_attribute():
    html_text = '<A HrEf="/x">x</A>'
    assert links(html_text) == ["https://example.com/x"]


def test_entity_decoded_href():
    html_text = '<a href="/search?a=1&amp;b=2">x</a>'
    assert links(html_text) == ["https://example.com/search?a=1&b=2"]


def test_quoted_gt_inside_attribute_does_not_truncate_tag():
    html_text = '<a title="a > b" href="/x">x</a>'
    assert links(html_text) == ["https://example.com/x"]


def test_href_inside_script_is_not_extracted():
    html_text = '<script>var s = "<a href=\\"/evil\\">";</script><a href="/real">x</a>'
    assert links(html_text) == ["https://example.com/real"]


def test_href_inside_style_and_comment_and_title_not_extracted():
    html_text = (
        "<!-- <a href=\"/commented\">x</a> -->"
        '<style>a::before { content: "<a href=\\"/css\\">"; }</style>'
        '<title>&lt;a href="/title"&gt;</title>'
        '<a href="/real">x</a>'
    )
    assert links(html_text) == ["https://example.com/real"]


def test_unterminated_script_consumes_to_end_of_document():
    html_text = '<script>var x = "<a href=\\"/evil\\">"'
    assert links(html_text) == []


def test_raw_text_tags_do_not_nest():
    # Per WHATWG spec, the first </script> ends the element, full stop.
    html_text = '<script>a</script>b</script><a href="/real">x</a>'
    assert links(html_text) == ["https://example.com/real"]


def test_base_href_changes_resolution_base():
    html_text = '<base href="https://cdn.example.com/assets/"><a href="img.png">x</a>'
    assert links(html_text) == ["https://cdn.example.com/assets/img.png"]


def test_only_first_base_href_counts():
    html_text = (
        '<base href="https://first.example.com/">'
        '<base href="https://second.example.com/">'
        '<a href="x">x</a>'
    )
    assert links(html_text) == ["https://first.example.com/x"]


def test_illegally_nested_a_tags_do_not_crash():
    html_text = '<a href="/outer"><a href="/inner">x</a></a>'
    assert links(html_text) == ["https://example.com/outer", "https://example.com/inner"]


def test_a_tag_without_href_is_skipped():
    html_text = '<a name="anchor">x</a><a href="/real">y</a>'
    assert links(html_text) == ["https://example.com/real"]


def test_fragment_and_query_preserved():
    html_text = '<a href="/x?a=1#frag">x</a>'
    assert links(html_text) == ["https://example.com/x?a=1#frag"]


def test_self_closing_anchor():
    html_text = '<a href="/x"/><a href="/y">y</a>'
    assert links(html_text) == ["https://example.com/x", "https://example.com/y"]


def test_hyphenated_attribute_ending_in_href_is_not_mistaken_for_href():
    # Regression: `href\s*=` with no boundary guard matched *inside*
    # `data-original-href=`, extracting the wrong value entirely.
    html_text = '<a data-original-href="/wrong" href="/right">x</a>'
    assert links(html_text) == ["https://example.com/right"]


def test_camelcase_attribute_ending_in_href_is_not_mistaken_for_href():
    html_text = '<a originalHref="/wrong" href="/right">x</a>'
    assert links(html_text) == ["https://example.com/right"]


def test_href_suffixed_attribute_with_no_real_href_yields_nothing():
    html_text = '<a data-original-href="/wrong">x</a>'
    assert links(html_text) == []
