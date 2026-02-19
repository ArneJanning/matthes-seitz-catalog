#!/usr/bin/env python3
"""
Scrape the complete Matthes & Seitz Berlin book catalog as structured JSON.

Covers all imprints: Matthes & Seitz Berlin, Friedenauer Presse, August Verlag.

Usage:
    matthes-seitz-catalog                          # Full scrape → catalog.json
    matthes-seitz-catalog --output books.json      # Custom output path
    matthes-seitz-catalog --limit 10               # Only 10 titles (testing)
    matthes-seitz-catalog --imprints matthes-seitz-berlin friedenauer-presse
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

__all__ = ["scrape_catalog", "main"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.matthes-seitz-berlin.de"
ALL_IMPRINTS = [
    "matthes-seitz-berlin",
    "friedenauer-presse",
    "august-verlag",
]

USER_AGENT = (
    "matthes-seitz-catalog/1.0 "
    "(+https://github.com/arnejanning/matthes-seitz-catalog)"
)

HEADERS = {"User-Agent": USER_AGENT}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("matthes-seitz-catalog")


# ---------------------------------------------------------------------------
# URL Collector — paginate all imprint catalogs
# ---------------------------------------------------------------------------


def collect_urls(
    imprints: list[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Collect all book detail URLs from imprint catalog pages.

    Args:
        imprints: List of imprint slugs to scrape. Defaults to all known imprints.
        limit: Maximum number of URLs to collect. None for unlimited.

    Returns:
        List of dicts with "url" and "imprint" keys.
    """
    if imprints is None:
        imprints = ALL_IMPRINTS

    all_books: list[dict] = []

    for imprint in imprints:
        catalog_url = f"{BASE_URL}/{imprint}/lieferbar.html"
        log.info("Collecting URLs for imprint: %s", imprint)

        try:
            resp = requests.get(catalog_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("  Skipping imprint %s: %s", imprint, e)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract total count from pager ("Anzahl: 1587")
        pager = soup.select_one("div#listpager p")
        total = 0
        if pager:
            m = re.search(r"(\d[\d.]*)", pager.get_text())
            if m:
                total = int(m.group(1).replace(".", ""))
        log.info("  %s: %d titles", imprint, total)

        # Extract URLs from first page
        books_on_page = _extract_urls_from_page(soup, imprint)
        all_books.extend(books_on_page)

        if limit and len(all_books) >= limit:
            return all_books[:limit]

        # Paginate remaining pages (24 items per page, 0-indexed ?p= param)
        if total > 24:
            num_pages = (total + 23) // 24
            for page_idx in range(1, num_pages):
                if limit and len(all_books) >= limit:
                    return all_books[:limit]

                page_url = f"{catalog_url}?p={page_idx}"
                time.sleep(1.0)
                try:
                    resp = requests.get(page_url, headers=HEADERS, timeout=30)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    books_on_page = _extract_urls_from_page(soup, imprint)
                    all_books.extend(books_on_page)
                    log.info(
                        "  Page %d/%d — %d URLs total",
                        page_idx + 1,
                        num_pages,
                        len(all_books),
                    )
                except requests.RequestException as e:
                    log.warning("  Failed page %d: %s", page_idx + 1, e)

    if limit:
        return all_books[:limit]
    return all_books


def _extract_urls_from_page(soup: BeautifulSoup, imprint: str) -> list[dict]:
    """Extract book URLs from a catalog listing page."""
    books = []
    for item in soup.select("li.item.item_product"):
        link = item.select_one("h3.title a")
        if link and link.get("href"):
            href = link["href"]
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            # Strip tracking params like ?lid=1
            href = re.sub(r"\?.*$", "", href)
            books.append({"url": href, "imprint": imprint})
    return books


# ---------------------------------------------------------------------------
# Detail Scraper — extract metadata from each book page
# ---------------------------------------------------------------------------


def scrape_books(book_urls: list[dict]) -> list[dict]:
    """Scrape detail pages for all collected book URLs.

    Args:
        book_urls: List of dicts with "url" and "imprint" keys.

    Returns:
        List of book metadata dicts.
    """
    results = []
    total = len(book_urls)

    for i, entry in enumerate(book_urls):
        url = entry["url"]
        imprint = entry["imprint"]
        log.info("Scraping %d/%d: %s", i + 1, total, url.split("/")[-1])

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            book = _parse_detail_page(resp.text, url, imprint)
            if book:
                results.append(book)
        except requests.RequestException as e:
            log.warning("  Failed: %s", e)

        if i < total - 1:
            time.sleep(0.5)

    return results


def _parse_detail_page(html: str, url: str, imprint: str) -> dict | None:
    """Parse a book detail page and extract structured metadata."""
    soup = BeautifulSoup(html, "html.parser")

    # Title (required)
    title_el = soup.select_one("h1.title")
    if not title_el:
        log.warning("  No title found, skipping")
        return None
    title = title_el.get_text(strip=True)

    # Subtitle (optional)
    subtitle_el = soup.select_one("h2.subtitle")
    subtitle = subtitle_el.get_text(strip=True) if subtitle_el else None

    # Authors
    author_els = soup.select("div.authors a.author")
    authors = [a.get_text(strip=True) for a in author_els]

    # ISBN — remove invisible span containing compact ISBN before extracting
    isbn = None
    number_el = soup.select_one("div.number")
    if number_el:
        for inv in number_el.select("span.invisible"):
            inv.decompose()
        text = number_el.get_text(strip=True)
        m = re.search(r"(978[\d-]{10,})", text)
        if m:
            isbn = m.group(1).strip()

    # Price
    price = None
    price_el = soup.select_one("div.price span")
    if price_el:
        price = price_el.get_text(strip=True)

    # Pages/Format (e.g. "92 Seiten, Klappenbroschur")
    info = None
    info_el = soup.select_one("div.info")
    if info_el:
        info = info_el.get_text(strip=True)

    # Publication date
    date = None
    date_el = soup.select_one("div.dateof")
    if date_el:
        text = date_el.get_text(strip=True)
        text = re.sub(r"^Veröffentlicht:\s*", "", text)
        date = text.strip()

    # Series (e.g. "Fröhliche Wissenschaft")
    series = None
    series_el = soup.select_one("div.serial a")
    if series_el:
        series = series_el.get_text(strip=True)

    # Keywords (plain comma-separated text, not links)
    keywords = []
    kw_el = soup.select_one("div.keywords")
    if kw_el:
        text = kw_el.get_text(strip=True)
        text = re.sub(r"^Schlagworte:\s*", "", text)
        keywords = [kw.strip() for kw in text.split(",") if kw.strip()]

    # Blurb / Description
    description = None
    desc_el = soup.select_one("div#pdesc div.description")
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    return {
        "url": url,
        "imprint": imprint,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "isbn": isbn,
        "price": price,
        "pages_binding": info,
        "year": date,
        "series": series,
        "keywords": keywords,
        "description": description,
    }


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


def scrape_catalog(
    imprints: list[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Scrape the complete catalog and return structured book data.

    This is the main programmatic entry point.

    Args:
        imprints: Imprint slugs to scrape. Defaults to all.
        limit: Max titles to scrape. None for all (~1800).

    Returns:
        List of book metadata dicts.
    """
    log.info("Phase 1: Collecting URLs from catalog pages...")
    book_urls = collect_urls(imprints=imprints, limit=limit)
    log.info("Collected %d URLs", len(book_urls))

    log.info("Phase 2: Scraping detail pages...")
    books = scrape_books(book_urls)
    log.info("Scraped %d books", len(books))

    return books


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def print_stats(books: list[dict]) -> None:
    """Print summary statistics about scraped data."""
    print(f"\n{'=' * 60}")
    print("Scrape Statistics")
    print(f"{'=' * 60}")
    n = max(len(books), 1)
    print(f"Total books:           {len(books)}")

    with_desc = sum(1 for b in books if b.get("description"))
    print(f"With description:      {with_desc} ({100 * with_desc // n}%)")

    with_kw = sum(1 for b in books if b.get("keywords"))
    print(f"With keywords:         {with_kw} ({100 * with_kw // n}%)")

    with_series = sum(1 for b in books if b.get("series"))
    print(f"With series:           {with_series}")

    with_isbn = sum(1 for b in books if b.get("isbn"))
    print(f"With ISBN:             {with_isbn}")

    # Imprint breakdown
    imprint_counts: dict[str, int] = {}
    for b in books:
        imp = b.get("imprint", "unknown")
        imprint_counts[imp] = imprint_counts.get(imp, 0) + 1
    print("\nBy imprint:")
    for imp, count in sorted(imprint_counts.items(), key=lambda x: -x[1]):
        print(f"  {imp:30s} {count:5d}")

    # Top series
    series_counts: dict[str, int] = {}
    for b in books:
        if b.get("series"):
            s = b["series"]
            series_counts[s] = series_counts.get(s, 0) + 1
    if series_counts:
        print("\nTop series:")
        for s, count in sorted(series_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {s:40s} {count:4d}")

    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Scrape the Matthes & Seitz Berlin book catalog as JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  matthes-seitz-catalog                                   # Full scrape → catalog.json
  matthes-seitz-catalog --output books.json               # Custom output file
  matthes-seitz-catalog --limit 10                        # Test with 10 titles
  matthes-seitz-catalog --imprints friedenauer-presse     # Single imprint
  matthes-seitz-catalog --stdout | jq '.[] | .title'      # Pipe to jq
""",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("catalog.json"),
        help="Output JSON file path (default: catalog.json)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write JSON to stdout instead of file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of titles to scrape (for testing)",
    )
    parser.add_argument(
        "--imprints",
        nargs="+",
        choices=ALL_IMPRINTS,
        default=None,
        help="Imprints to scrape (default: all)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress logging",
    )
    args = parser.parse_args()

    if args.quiet:
        log.setLevel(logging.WARNING)

    books = scrape_catalog(imprints=args.imprints, limit=args.limit)

    if not books:
        log.error("No books scraped")
        sys.exit(1)

    if not args.quiet:
        print_stats(books)

    json_output = json.dumps(books, ensure_ascii=False, indent=2)

    if args.stdout:
        print(json_output)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_output, encoding="utf-8")
        log.info("Written %d books to %s", len(books), args.output)


if __name__ == "__main__":
    main()
