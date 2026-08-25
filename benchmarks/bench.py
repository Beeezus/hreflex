"""Throughput comparison: hreflex vs selectolax vs lxml.html vs BeautifulSoup,
over real-world pages of varying size. Median of N repetitions, single
machine, single-threaded. Reports wall time and MB/s per page per library.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from lxml import html as lxml_html
from selectolax.parser import HTMLParser

from hreflex import extract_links

try:
    from hreflex.native import extract_links as extract_links_native
except ImportError:
    extract_links_native = None

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPS = 7

PAGES = [
    ("hackernews.html", "https://news.ycombinator.com/"),
    ("midnightlabs.html", "https://www.midnightlabs.ai/"),
    ("wikipedia.html", "https://en.wikipedia.org/wiki/Web_scraping"),
    ("ceartas_home.html", "https://www.ceartas.io/"),
]


def run_hreflex(html_text, base_url):
    return list(extract_links(html_text, base_url))


def run_hreflex_native(html_text, base_url):
    return extract_links_native(html_text, base_url)


def run_selectolax(html_text, base_url):
    return [
        urljoin(base_url, n.attributes.get("href"))
        for n in HTMLParser(html_text).css("a[href]")
        if n.attributes.get("href")
    ]


def run_lxml(html_text, base_url):
    tree = lxml_html.fromstring(html_text)
    return [urljoin(base_url, href) for href in tree.xpath("//a/@href")]


def run_bs4(html_text, base_url):
    soup = BeautifulSoup(html_text, "html.parser")
    return [
        urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)
    ]


LIBRARIES = [
    ("hreflex", run_hreflex),
    ("hreflex.native", run_hreflex_native),
    ("selectolax", run_selectolax),
    ("lxml.html", run_lxml),
    ("BeautifulSoup", run_bs4),
]
if extract_links_native is None:
    LIBRARIES = [(name, fn) for name, fn in LIBRARIES if name != "hreflex.native"]


def time_one(fn, html_text, base_url):
    samples = []
    for _ in range(REPS):
        start = time.perf_counter()
        links = fn(html_text, base_url)
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), len(links)


def main():
    rows = []
    for filename, base_url in PAGES:
        path = FIXTURES_DIR / filename
        html_text = path.read_text(encoding="utf-8")
        size_mb = len(html_text.encode("utf-8")) / (1024 * 1024)
        for lib_name, fn in LIBRARIES:
            median_s, n_links = time_one(fn, html_text, base_url)
            mb_per_s = size_mb / median_s if median_s > 0 else float("inf")
            rows.append((filename, size_mb, lib_name, median_s, mb_per_s, n_links))

    header = f"{'page':<20}{'size(MB)':>10}{'library':>16}{'median(ms)':>13}{'MB/s':>10}{'links':>8}"
    print(header)
    print("-" * len(header))
    for filename, size_mb, lib_name, median_s, mb_per_s, n_links in rows:
        print(
            f"{filename:<20}{size_mb:>10.2f}{lib_name:>16}"
            f"{median_s * 1000:>13.2f}{mb_per_s:>10.1f}{n_links:>8}"
        )


if __name__ == "__main__":
    main()
