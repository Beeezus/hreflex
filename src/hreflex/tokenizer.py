"""A no-DOM, single-pass tokenizer that extracts <a href> links from HTML.

Unlike a general HTML parser (selectolax, lxml, BeautifulSoup), this never
builds a tree. It only reacts to the handful of constructs that matter for
link extraction: comments, CDATA, raw-text elements (script/style/textarea/
title, whose content must never be scanned for tags), and <a href> itself.

Hrefs are yielded exactly as they appear in the document (only HTML-entity
decoded) -- no URL resolution. Turning a relative href into an absolute URL
needs a base URL, and the caller is in a better position to supply and vet
one than this tokenizer is; see the README for why that's a deliberate
boundary rather than a missing feature.

Scanning is a hand-driven loop, not one big backtracking regex over the
whole document. An earlier version used a single `(?:...)*` quantifier for
a tag's attribute body; on adversarial input with an opening tag but no
closing '>' anywhere in the rest of the document, that quantifier fails by
backtracking one character at a time, and re-finditer retries the same
failure at every subsequent tag-open position -- O(n^2) on a string like
"<a " * 200_000, confirmed by measurement (quadratic growth: 1k chars in
0.08s, 5k in 2.1s, 10k in 8.6s). The fix here is structural: each step
below advances the scan position monotonically and never revisits text,
using `re.search`/`str.find` (both O(distance scanned), C-level, no
backtracking) to jump to the next relevant character. If a tag or quoted
attribute value is ever left unterminated, per the WHATWG tokenizer state
machine that also means the rest of the document belongs to it (a browser
gets "confused" the same way) -- so stopping the whole scan at that point
is spec-consistent, not just an optimization.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator

_RAW_TEXT_TAGS = ("script", "style", "textarea", "title")

_OPENER_RE = re.compile(
    r"(?P<comment><!--)"
    r"|(?P<cdata><!\[CDATA\[)"
    r"|<(?P<rawtag>script|style|textarea|title)\b"
    r"|(?P<a><a\b)",
    re.IGNORECASE,
)

_RAW_TEXT_CLOSE_RE = {
    tag: re.compile(r"</" + tag + r"\s*>", re.IGNORECASE) for tag in _RAW_TEXT_TAGS
}

_QUOTE_OR_GT = re.compile(r"""[>'"]""")

_HREF_RE = re.compile(
    r"""(?<![A-Za-z0-9_-])href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s'"=<>`]+))""",
    re.IGNORECASE,
)


def _find_tag_end(text: str, pos: int) -> int | None:
    """Index of the unquoted '>' closing the tag body starting at pos, or
    None if the document runs out first. Jumps via re.search/str.find --
    O(distance scanned), no per-character Python loop, no backtracking.
    """
    i = pos
    while True:
        match = _QUOTE_OR_GT.search(text, i)
        if match is None:
            return None
        if match.group() == ">":
            return match.start()
        close = text.find(match.group(), match.start() + 1)
        if close == -1:
            return None
        i = close + 1


def _extract_href(tag_body: str) -> str | None:
    match = _HREF_RE.search(tag_body)
    if match is None:
        return None
    return next(g for g in match.groups() if g is not None)


def extract_links(html_text: str) -> Iterator[str]:
    """Yield the raw `href` value of every `<a href>` in html_text, in
    document order, HTML-entity decoded but otherwise untouched -- relative
    hrefs stay relative. Resolving against a base URL is the caller's job.
    """
    pos = 0
    length = len(html_text)

    while pos < length:
        match = _OPENER_RE.search(html_text, pos)
        if match is None:
            return

        if match.group("comment"):
            end = html_text.find("-->", match.end())
            if end == -1:
                return
            pos = end + 3
            continue

        if match.group("cdata"):
            end = html_text.find("]]>", match.end())
            if end == -1:
                return
            pos = end + 3
            continue

        rawtag = match.group("rawtag")
        if rawtag is not None:
            open_end = _find_tag_end(html_text, match.end())
            if open_end is None:
                return
            close_match = _RAW_TEXT_CLOSE_RE[rawtag.lower()].search(html_text, open_end + 1)
            if close_match is None:
                return
            pos = close_match.end()
            continue

        # <a ...>: needs this tag's own closing '>'.
        tag_end = _find_tag_end(html_text, match.end())
        if tag_end is None:
            return
        tag_body = html_text[match.end() : tag_end]

        href = _extract_href(tag_body)
        if href is not None:
            yield html.unescape(href)

        pos = tag_end + 1
