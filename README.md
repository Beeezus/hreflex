# hreflex

[![tests](https://github.com/Beeezus/hreflex/actions/workflows/test.yml/badge.svg)](https://github.com/Beeezus/hreflex/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

A single-pass, no-DOM HTML tokenizer that extracts `<a href>` links —
without building a tree. The primary implementation is Rust/PyO3
(`hreflex.native`), **30-90x faster than `selectolax`** on real pages. A
pure-Python implementation (`hreflex`) also exists but is legacy — see
[Legacy: pure-Python implementation](#legacy-pure-python-implementation).

```python
from hreflex.native import extract_links

html = '<a href="/about">About</a>'
list(extract_links(html))
# ['/about']
```

`extract_links` takes just the HTML string and yields each `href` exactly
as it appears in the document (HTML-entity decoded, otherwise untouched).
It does not resolve relative URLs against a base — see
[Why no base URL / resolution](#why-no-base-url--resolution).

## Why

General-purpose HTML parsers (`selectolax`, `lxml`, `BeautifulSoup`) all do
full HTML5 tree construction — tokenization, the insertion-mode state
machine, implicit tag closing — before an `a[href]` query ever runs. If all
you actually want is anchor hrefs, you never need a tree. `hreflex` reacts
only to the handful of constructs that matter (comments, CDATA, raw-text
elements, `<a href>`) and skips the rest, in one linear pass.

This is the same idea behind Cloudflare's `lol_html` (a Rust streaming
rewriter with no DOM) — applied here as a from-scratch exercise rather
than a binding to an existing engine. Full background on how this project
got here, including a first attempt that lost to `selectolax`, is in
[DESIGN.md](DESIGN.md).

## Installation

Requires Python 3.10+. Not yet published to PyPI — install from source.

```bash
git clone git@github.com:Beeezus/hreflex.git
cd hreflex
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release -m native/Cargo.toml
```

Building the native extension requires a Rust toolchain
([rustup](https://rustup.rs)). CI (`.github/workflows/wheels.yml`) builds
installable wheels for Linux (x86_64 + aarch64), macOS (universal2), and
Windows (x64) on every push — download the artifact from a run and
`pip install` it directly if you'd rather skip building locally.

## Usage

```python
from hreflex.native import extract_links

html = '<a href="/about">About</a><a href="https://other.com/b">B</a>'
list(extract_links(html))
# ['/about', 'https://other.com/b']
```

## Why no base URL / resolution

Earlier versions of this API took a `base_url` argument and resolved every
href against it (honoring an in-document `<base href>`, per spec). That
was dropped: resolving a relative URL requires deciding *which* URL-join
algorithm to use (WHATWG vs. RFC 3986 disagree on edge cases — see
[DESIGN.md](DESIGN.md)) and it's a decision the caller is better placed to
make than a link-extraction tokenizer is. `hreflex` now does one thing:
tell you every `href` that's in the document, verbatim. If you need
absolute URLs, resolve them yourself:

```python
from urllib.parse import urljoin

base = "https://example.com/"
absolute = [urljoin(base, href) for href in extract_links(html)]
```

## What it does not do

- No DOM, no tree, no way to query anything other than links.
- No URL resolution — see above.
- No bytes/charset-detection input — pass already-decoded `str` (e.g. from
  `httpx.Response.text`, which already does charset detection correctly).
- No streaming/incremental parsing across network chunks — the whole
  document is scanned as one in-memory string.

These are deliberate boundaries, not oversights — see [DESIGN.md](DESIGN.md)
for the reasoning behind each.

## Correctness

Tested four ways (`tests/test_*.py`), all run against both backends
wherever `hreflex.native` is built:

- **Conformance** (`test_conformance.py`) — targeted cases covering what
  regex-based HTML handling is famous for getting wrong: raw-text content,
  unterminated/malformed tags, quoted `>` inside an attribute, mixed-case
  tags, entity-encoded hrefs.
- **Oracle cross-validation** (`test_oracle.py`) — diffs output against
  `selectolax` (a real, spec-conformant parser) on real pages.
- **ReDoS/timing** (`test_redos.py`) — hard timeout assertions on
  adversarial input, since crawled HTML is untrusted; every pattern here
  is built to avoid catastrophic backtracking.
- **Parity** (`test_parity.py`) — the two backends are the same algorithm
  in two languages; this asserts they actually agree. `native/src/scan.rs`
  also carries its own `cargo test` unit tests.

## Development

```bash
pip install -e ".[dev]"
maturin develop --release -m native/Cargo.toml   # build the native extension
pytest -q                                        # runs both backends
cargo test --release --manifest-path native/Cargo.toml
```

## Benchmark

See `benchmarks/bench.py` — run with `python benchmarks/bench.py`. Median
of 7 repetitions, single machine, single-threaded, four real pages of
varying size. All libraries extract the same raw `href` values (no URL
resolution), which doubles as a correctness cross-check: every column
agrees on link count for every page.

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

`hreflex.native` beats `selectolax` by 30-90x. `hreflex` (pure Python)
*loses* to `selectolax`/`lxml.html` by ~2-3x — the interpreter overhead of
crossing the Python/C boundary once per tag dominates, which is exactly
why the native port exists. Full methodology and re-measurement notes are
in [DESIGN.md](DESIGN.md).

## Legacy: pure-Python implementation

```python
from hreflex import extract_links  # pure Python — legacy, no auto-fallback
```

`hreflex` (no `.native`) is the original reference implementation: same
algorithm, same test suite, but ~2-3x *slower* than `selectolax`/`lxml`
because every tag still costs a Python↔C round trip. It's kept around for
reference and as a dependency-free fallback where a Rust toolchain isn't
available, but **it is deprecated** and will be removed once native wheels
are published to PyPI and installable with a plain `pip install hreflex`.
New code should use `hreflex.native`.

## License

[MIT](LICENSE)
