# hreflex

A single-pass, no-DOM HTML tokenizer that extracts `<a href>` links —
without building a tree.

## Why

General-purpose HTML parsers (`selectolax`, `lxml`, `BeautifulSoup`) all do
full HTML5 tree construction — tokenization, the insertion-mode state
machine, implicit tag closing — before a `a[href]` query ever runs. If all
you actually want is anchor hrefs, you never need a tree. `hreflex` reacts
to the handful of constructs that matter (comments, CDATA, raw-text
elements, `<base href>`, `<a href>`) and skips the rest, in one linear pass
implemented as a handful of compiled `re` patterns.

This is the same idea behind Cloudflare's `lol_html` (a Rust streaming
rewriter with no DOM) — applied here as a from-scratch Python exercise
rather than a binding to an existing engine.

## Usage

```python
from hreflex import extract_links

html = '<a href="/about">About</a>'
list(extract_links(html, base_url="https://example.com/"))
# ['https://example.com/about']
```

`<base href>` is honored if present, per spec (first one wins).

## What it does not do

- No DOM, no tree, no way to query anything other than links.
- No bytes/charset-detection input — pass already-decoded `str` (e.g. from
  `httpx.Response.text`, which already does charset detection correctly).
- No streaming/incremental parsing across network chunks — the whole
  document is scanned as one in-memory string.

These are deliberate v1 boundaries, not oversights — see the design
write-up below for the reasoning behind each.

## Correctness

Tested three ways:
- **Conformance cases** (`tests/test_conformance.py`) covering the specific
  failure modes regex-based HTML handling is famous for getting wrong:
  raw-text content (script/style/textarea/title) that must never be
  scanned for tags, unterminated/malformed tags, quoted `>` inside an
  attribute value, mixed-case tags, entity-encoded hrefs, `<base href>`.
- **Oracle cross-validation** (`tests/test_oracle.py`) — diffs `hreflex`'s
  output against `selectolax` (a real, spec-conformant parser) on real
  pages (Hacker News, a live marketing site). Disagreements are either a
  bug here or a genuine edge case worth naming.
- **ReDoS/timing tests** (`tests/test_redos.py`) — crawled HTML is
  untrusted input; every pattern here is built from non-overlapping
  character classes (no `(a+)+`-style nesting) specifically to avoid
  catastrophic backtracking, and that's asserted with hard timeouts on
  adversarial input, not just claimed.

  This is not a hypothetical concern the tests exist to preempt — it's
  what actually happened while building this. An earlier version matched
  each tag's attribute body with one `(?:"[^"]*"|'[^']*'|[^'">])*`
  quantifier inside a single `re.finditer` pass. On input with an opening
  tag but no closing `>` anywhere later in the document (`"<a " * n`), that
  quantifier backtracks the full remaining length before failing, and
  `finditer` retries the same failure at every subsequent `<a` — confirmed
  quadratic by direct measurement (1k chars: 0.08s, 5k: 2.1s, 10k: 8.6s).
  The fix is structural, in `tokenizer.py`'s `_find_tag_end`: a hand-driven
  scan loop that advances position monotonically via `re.search`/`str.find`
  and, per the WHATWG tokenizer spec, treats "no closing `>` found" as
  proof that the rest of the document is unparseable content — so it stops
  the whole scan there instead of retrying, which is simultaneously the
  spec-correct behavior and what makes the worst case O(n) instead of
  O(n²).

## Benchmark

See `benchmarks/bench.py`. Run with `python benchmarks/bench.py`. Median of
7 repetitions, single machine, single-threaded, four real pages of varying
size (Hacker News, a marketing SPA, a Wikipedia article, a 3.9MB Framer
homepage). All four libraries agree exactly on the link count for every
page — a useful correctness cross-check, not just a speed comparison.

```
page                  size(MB)         library   median(ms)      MB/s   links
-----------------------------------------------------------------------------
hackernews.html           0.03         hreflex         6.52       5.1     229
hackernews.html           0.03      selectolax         4.68       7.1     229
hackernews.html           0.03       lxml.html         4.21       7.9     229
hackernews.html           0.03   BeautifulSoup        44.23       0.8     229
midnightlabs.html         0.38         hreflex        20.69      18.4      32
midnightlabs.html         0.38      selectolax         9.17      41.5      32
midnightlabs.html         0.38       lxml.html         9.05      42.1      32
midnightlabs.html         0.38   BeautifulSoup        56.74       6.7      32
wikipedia.html            0.23         hreflex        20.41      11.2     480
wikipedia.html            0.23      selectolax        14.26      16.1     480
wikipedia.html            0.23       lxml.html        11.38      20.1     480
wikipedia.html            0.23   BeautifulSoup        95.96       2.4     480
ceartas_home.html         3.90         hreflex       220.15      17.7     151
ceartas_home.html         3.90      selectolax        70.86      55.0     151
ceartas_home.html         3.90       lxml.html        84.24      46.3     151
ceartas_home.html         3.90   BeautifulSoup       853.69       4.6     151
```

**The honest result: `hreflex` loses to `selectolax` and `lxml.html` by
roughly 2-3x, and beats `BeautifulSoup` by 4-8x.** This is the outcome the
design writeup predicted, not a surprise: `selectolax`/`lxml` do their
*entire* tokenize-and-tree-construct pass inside C with no round trips back
into the Python interpreter per tag. `hreflex` avoids building a tree, but
still crosses the Python/C boundary several times per anchor — one
`re.search` to find the opener, one or two more inside `_find_tag_end`, one
`re.search` for the href attribute, `html.unescape`, `urljoin` — and each
crossing carries real per-call Python overhead that a pure-C pass never
pays. Doing structurally less work doesn't win if the language boundary is
crossed more often; that tradeoff is the actual finding here, not "regex
extraction is faster than a real parser." Against `BeautifulSoup` — whose
tree is built in Python, not C — the DOM-free design wins outright, which
is the fairer apples-to-apples comparison for "what does skipping tree
construction actually buy you, holding the implementation language fixed."

## Design notes

Full reasoning for each design decision (why regex over a hand-written
character loop, why quote-aware tag bodies, why `<base>` support, why
`html.unescape` instead of a hand-rolled entity table, why `str` input
only) is in the project's planning notes — the short version is: every
choice here was made by asking "does doing this ourselves reduce risk or
just add it," and several things that would look like part of a "build it
from scratch" exercise (entity decoding, charset detection) were
deliberately left to already-correct code instead.
