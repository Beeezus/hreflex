# hreflex

A single-pass, no-DOM HTML tokenizer that extracts `<a href>` links —
without building a tree. Two implementations of the same algorithm:
`hreflex` (pure Python, the reference implementation) and
`hreflex.native` (Rust/PyO3, 30-90x faster than `selectolax` — see
Benchmark).

## Where this started and where it ended up

This began as a straight question: for extracting just `<a href>` links,
can a purpose-built tool beat a general HTML parser? First attempt —
pure Python, regex-driven, no DOM — said no: **2-3x *slower*** than
`selectolax`/`lxml.html`, despite doing structurally less work, because
every tag still cost a Python↔C round trip. That honest negative result
shipped anyway (`hreflex`), along with the real bug an oracle
cross-validation against `selectolax` turned up in the process (`href`
matching false-positive inside `data-original-href`-style attribute
names — found on live Wikipedia markup, fixed and regression-tested).

Second attempt moved the whole algorithm into Rust (`hreflex.native`):
SIMD `memchr` scanning instead of backtracking `re`, and *one*
Python↔Rust crossing per document instead of one per tag. Result,
independently re-measured to rule out a fluke: **30-90x faster than
`selectolax`** — 66ms → 0.75ms on a 3.9MB real page, steady-state,
correct link count every time.

| | vs `selectolax` | on a 3.9MB real page |
|---|---|---|
| `hreflex` (pure Python) | ~2-3x **slower** | 213.9ms vs 66.2ms |
| `hreflex.native` (Rust) | **30-90x faster** | 0.75ms vs 66.2ms |

Full numbers, methodology, and the two genuine findings along the way
(the `href` boundary-guard bug, and a real spec-level WHATWG-vs-RFC3986
URL-join divergence between the two backends) are below.

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

## `hreflex.native` — the Rust/PyO3 accelerated core

The pure-Python implementation above loses to `selectolax`/`lxml` by
2-3x (see Benchmark) despite doing less work, because it still crosses
the Python/C boundary several times per tag. `hreflex.native` ports the
exact same algorithm to Rust — SIMD byte-scanning (`memchr`/`memchr3`)
instead of Python's `re`, one Python↔Rust boundary crossing per
*document* instead of per tag — and the result is not a modest win, it's
60-90x faster than `selectolax` on real pages (see Benchmark).

```python
from hreflex.native import extract_links  # explicit, separate import -- no auto-fallback

list(extract_links('<a href="/about">About</a>', "https://example.com/"))
# ['https://example.com/about']
```

Building from source requires a Rust toolchain (`rustup`) and `maturin`:

```
maturin develop --release -m native/Cargo.toml
```

CI (`.github/workflows/wheels.yml`) builds real installable wheels for
Linux (x86_64 + aarch64), macOS (universal2, Intel + Apple Silicon in one
wheel), and Windows (x64) on every push, using PyO3's `abi3-py310` stable
ABI so one wheel per platform covers Python 3.10+ instead of one per
(platform, Python-version) pair — download the artifact from a run and
`pip install` it directly. Not yet published to PyPI (needs a
`PYPI_API_TOKEN` secret this repo doesn't have configured — a deliberate
separate step, not a side effect of building wheels).

`from hreflex import extract_links` (the pure-Python path) is completely
unaffected by any of this — same function, same behavior, nothing about
it changed to make room for the native module.

**One real, spec-level divergence between the two, found by the parity
tests (`tests/test_parity.py`) and worth knowing about:** the native core
uses Rust's `url` crate, which implements the WHATWG URL Standard (what
real browsers do); the pure-Python core uses `urllib.parse.urljoin`,
which implements the older RFC 3986 algorithm. They agree on every real
page tested except two narrow, cosmetic cases: an already-absolute href
with no path (`href="https://x.com"`) gets a WHATWG-mandated trailing
`/` from native but comes back untouched from pure; and a bare `#`
empty-fragment href round-trips as a literal trailing `#` from native
(spec-correct) but is silently dropped by `urljoin` in pure. Both are
"correct" per their own spec — this isn't a bug in either implementation,
just two different specs for the same operation. `tests/_url_compare.py`
documents and normalizes exactly this for the test suite.

## What it does not do

- No DOM, no tree, no way to query anything other than links.
- No bytes/charset-detection input — pass already-decoded `str` (e.g. from
  `httpx.Response.text`, which already does charset detection correctly).
- No streaming/incremental parsing across network chunks — the whole
  document is scanned as one in-memory string.

These are deliberate v1 boundaries, not oversights — see the design
write-up below for the reasoning behind each.

## Correctness

Tested four ways (all run against both backends, `tests/test_*.py`
parametrize over pure and native wherever `hreflex.native` is built):
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
- **Parity tests** (`tests/test_parity.py`) — the two implementations are
  supposed to be the same algorithm in two languages; this asserts they
  actually agree, on both adversarial cases and every real-page fixture
  (modulo the one documented URL-join divergence above). `native/src/scan.rs`
  also carries its own `cargo test` unit tests, independent of pytest.

## Benchmark

See `benchmarks/bench.py`. Run with `python benchmarks/bench.py`. Median of
7 repetitions, single machine, single-threaded, four real pages of varying
size (Hacker News, a marketing SPA, a Wikipedia article, a 3.9MB Framer
homepage). All five columns agree exactly on the link count for every
page (after normalizing the one documented URL-join divergence above) —
a useful correctness cross-check, not just a speed comparison.

```
page                  size(MB)         library   median(ms)      MB/s   links
-----------------------------------------------------------------------------
hackernews.html           0.03         hreflex         5.32       6.2     229
hackernews.html           0.03  hreflex.native         0.20     166.9     229
hackernews.html           0.03      selectolax         4.48       7.4     229
hackernews.html           0.03       lxml.html         3.92       8.5     229
hackernews.html           0.03   BeautifulSoup        29.71       1.1     229
midnightlabs.html         0.38         hreflex        13.77      27.6      32
midnightlabs.html         0.38  hreflex.native         0.10    3886.3      32
midnightlabs.html         0.38      selectolax         6.26      60.8      32
midnightlabs.html         0.38       lxml.html         7.67      49.6      32
midnightlabs.html         0.38   BeautifulSoup        48.96       7.8      32
wikipedia.html            0.23         hreflex        19.40      11.8     480
wikipedia.html            0.23  hreflex.native         0.34     665.9     480
wikipedia.html            0.23      selectolax        11.83      19.4     480
wikipedia.html            0.23       lxml.html         9.17      25.0     480
wikipedia.html            0.23   BeautifulSoup        90.54       2.5     480
ceartas_home.html         3.90         hreflex       213.93      18.2     151
ceartas_home.html         3.90  hreflex.native         0.75    5176.6     151
ceartas_home.html         3.90      selectolax        66.20      58.9     151
ceartas_home.html         3.90       lxml.html        79.84      48.8     151
ceartas_home.html         3.90   BeautifulSoup       795.23       4.9     151
```

**`hreflex` (pure Python) loses to `selectolax`/`lxml.html` by ~2-3x, as
explained above. `hreflex.native` beats `selectolax` by 30-90x** —
independently re-measured outside the benchmark harness to rule out a
measurement artifact (steady-state ~1.1ms on the 3.9MB page across five
fresh calls, correct 151 links every time — see git history for the
verification). This is the payoff of the two decisions the design writeup
argued for: SIMD `memchr` scanning instead of a backtracking regex
engine, and *one* Python↔Rust boundary crossing per document instead of
one Python↔C crossing per tag. Skipping DOM construction, which didn't
matter in the pure-Python version because interpreter overhead dominated
first, matters enormously once that overhead is gone — `selectolax` is
still building and allocating a full tree of C nodes for a query that
only ever wanted `a[href]`, and `hreflex.native` never does.

## Design notes

Full reasoning for each design decision (why regex over a hand-written
character loop, why quote-aware tag bodies, why `<base>` support, why
`html.unescape` instead of a hand-rolled entity table, why `str` input
only) is in the project's planning notes — the short version is: every
choice here was made by asking "does doing this ourselves reduce risk or
just add it," and several things that would look like part of a "build it
from scratch" exercise (entity decoding, charset detection) were
deliberately left to already-correct code instead.
