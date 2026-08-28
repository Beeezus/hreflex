# Design notes

## Where this started and where it ended up

This began as a straight question: for extracting just `<a href>` links,
can a purpose-built tool beat a general HTML parser? First attempt — pure
Python, regex-driven, no DOM — said no: **2-3x *slower*** than
`selectolax`/`lxml.html`, despite doing structurally less work, because
every tag still cost a Python↔C round trip. That honest negative result
shipped anyway (`hreflex`), along with a real bug an oracle
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

## Dropping `base_url`

v1 took a `base_url` argument and resolved every href against it (per
spec, honoring the first in-document `<base href>`). That surfaced a real
divergence between the two backends: the pure-Python core used
`urllib.parse.urljoin` (RFC 3986), the native core used Rust's `url` crate
(WHATWG URL Standard). They agreed on every real page tested except two
narrow, cosmetic cases — an already-absolute href with no path
(`href="https://x.com"`) gets a WHATWG-mandated trailing `/` from native
but comes back untouched from pure, and a bare `#` empty-fragment href
round-trips as a literal trailing `#` from native (spec-correct) but is
silently dropped by `urljoin` in pure. Both were "correct" per their own
spec — not a bug in either implementation, just two different specs for
the same operation.

Rather than pick a spec to standardize on (or make callers care which one
they got), `base_url` and all URL resolution were removed. `extract_links`
now yields hrefs exactly as found in the document. This has two effects:
it deletes the WHATWG-vs-RFC3986 divergence entirely (there's no join left
to disagree about — the two backends are now byte-identical on every
tested page), and it moves the URL-join decision to the caller, who
usually already knows which semantics their pipeline needs.

`<base href>` is no longer special-cased either: with no resolution
happening, there's nothing left for it to influence, so it's now just
inert data like any other non-`<a>` tag.

## Why regex/hand-written-loop over a real tokenizer state machine

Every choice here was made by asking "does doing this ourselves reduce
risk or just add it." A few things that would look like part of a
"build it from scratch" exercise were deliberately left to already-correct
code instead: entity decoding (`html.unescape` / the `html-escape` crate,
not a hand-rolled table) and charset detection (explicitly out of scope —
callers pass already-decoded `str`).

## ReDoS and the O(n²) regression

This is not a hypothetical concern the test suite exists to preempt — it's
what actually happened while building this. An earlier version matched
each tag's attribute body with one `(?:"[^"]*"|'[^']*'|[^'">])*` quantifier
inside a single `re.finditer` pass. On input with an opening tag but no
closing `>` anywhere later in the document (`"<a " * n`), that quantifier
backtracks the full remaining length before failing, and `finditer` retries
the same failure at every subsequent `<a` — confirmed quadratic by direct
measurement (1k chars: 0.08s, 5k: 2.1s, 10k: 8.6s).

The fix is structural, in `tokenizer.py`'s `_find_tag_end`: a hand-driven
scan loop that advances position monotonically via `re.search`/`str.find`
and, per the WHATWG tokenizer spec, treats "no closing `>` found" as proof
that the rest of the document is unparseable content — so it stops the
whole scan there instead of retrying, which is simultaneously the
spec-correct behavior and what makes the worst case O(n) instead of O(n²).
`native/src/scan.rs` ports the same invariant using `memchr`/`memchr3`.

## Benchmark methodology

`benchmarks/bench.py`, median of 7 repetitions, single machine,
single-threaded, four real pages of varying size (Hacker News, a marketing
SPA, a Wikipedia article, a 3.9MB Framer homepage). The 30-90x number was
independently re-measured outside the benchmark harness to rule out a
measurement artifact (steady-state ~1.1ms on the 3.9MB page across five
fresh calls, correct 151 links every time). This is the payoff of two
decisions: SIMD `memchr` scanning instead of a backtracking regex engine,
and one Python↔Rust boundary crossing per document instead of one
Python↔C crossing per tag. Skipping DOM construction didn't matter in the
pure-Python version because interpreter overhead dominated first — it
matters enormously once that overhead is gone, since `selectolax` is still
building and allocating a full tree of C nodes for a query that only ever
wanted `a[href]`, and `hreflex.native` never does.

## PyPI / distribution

Wheels are built by CI (`.github/workflows/wheels.yml`) using PyO3's
`abi3-py310` stable ABI, so one wheel per platform covers Python 3.10+
instead of one per (platform, Python-version) pair. Not yet published to
PyPI — that needs a `PYPI_API_TOKEN` secret this repo doesn't have
configured, a deliberate separate step, not a side effect of building
wheels.
