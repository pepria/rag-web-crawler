"""
Unibo Website Scraper
BFS crawler for www.unibo.it / corsi.unibo.it / www.eng.unibo.it.
Converts HTML pages to Markdown and extracts text from course PDFs.

Usage:
  python scraper.py                                         # default seeds, 5000 pages
  python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence
  python scraper.py --url URL1 --url URL2 --max-pages 200
  python scraper.py --retry
"""

import argparse
import asyncio
import heapq
import re
import json
import io
import httpx
from itertools import count
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from pypdf import PdfReader


# ── Crawl config ──────────────────────────────────────────────────────────────

ALLOWED_DOMAINS = {"www.unibo.it", "corsi.unibo.it", "www.eng.unibo.it"}

SYLLABUS_SOURCE_DOMAIN = "corsi.unibo.it"

DEFAULT_SEED_URLS = [
    "https://www.unibo.it/en/homepage",
    "https://www.unibo.it/en/enrolled-students",
    "https://corsi.unibo.it/2cycle/artificial-intelligence",
]

# Predefined course sets for --preset. Each entry is a list of seed URLs.
# Faculty pages are included so professor /sitoweb/ links are discovered.
PRESET_URLS: dict[str, list[str]] = {
    "ai-msc": [
        "https://corsi.unibo.it/2cycle/artificial-intelligence",
    ],
    "cs-msc": [
        "https://corsi.unibo.it/2cycle/ComputerScience",
    ],
    "data-science": [
        "https://corsi.unibo.it/2cycle/StatisticalSciences",
    ],
    "robotics": [
        "https://corsi.unibo.it/2cycle/AutomotiveEngineering",
    ],
}

BOOSTED_PREFIXES = ("/en/study", "/en/research", "/sitoweb/")

SHALLOW_URL_PATTERNS = ["/notice-board", "/unibomagazine", "/events", "/news"]

SKIP_URL_FRAGMENTS = [
    "/it/", "/magistrale/", "/laurea/",
    "@@multilingual-selector", "/uniboweb", "/concilium", "/speis",
    "/university/support-the-alma-mater",
    "/university/transparent-administration",
    "/university/contracting-and-sales",
    "/research/projects-and-initiatives",
    "#", "login", "logout",
    "sol/welcome", "almaesami", "solcampus",
    "timetable", "exam-dates",
    "about-the-website", "accessibility",
    "cookie", "privacy-policy",
    "@@print", "?print", "?search=", "?q=",
]

SKIP_EXTENSIONS = {".docx", ".xlsx", ".zip", ".ppt", ".pptx", ".doc"}

COURSE_SUBPAGES = [
    "overview", "admission", "programme", "faculty", "studying",
    "contacts", "course-structure-diagram", "opportunities",
    "how-to-enrol", "guidance", "prospects", "job-opportunities",
    "notice-board", "advisory-board", "degree-programme-tutor",
    "balancing-study-and-work", "registering-for-subsequent-years",
    "lecture-attendance", "final-examination", "examinations",
    "degree-programme-director-and-board", "degree-committees",
    "student-administration-offices", "programme-quality",
]

CHECKPOINT_INTERVAL = 20


# ── Crawler configs ───────────────────────────────────────────────────────────

_MD_OPTIONS = {"ignore_images": True, "body_width": 0, "tables": True, "unicode_snob": True}

CRAWLER_CONFIG = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(options={**_MD_OPTIONS, "ignore_links": False}),
    wait_until="domcontentloaded",
    page_timeout=30000,
    verbose=False,
    css_selector="main, #content, .page-content, article, [role='main'], body",
)

TITLES_ONLY_CONFIG = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(options={**_MD_OPTIONS, "ignore_links": False}),
    wait_until="domcontentloaded",
    page_timeout=30000,
    verbose=False,
    css_selector="h1, h2, h3, h4, .title, [class*='title'], [class*='heading']",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def url_to_filename(url: str, ext: str = ".md") -> str:
    parsed = urlparse(url)
    name = parsed.netloc + parsed.path
    name = re.sub(r"[^\w\-]", "_", name).strip("_")
    return name[:180] + ext


def is_shallow_url(url: str) -> bool:
    return any(pat in url for pat in SHALLOW_URL_PATTERNS)


def collect_links(result, source_url: str) -> tuple[list[str], list[str], list[str]]:
    """Return (page_links, syllabus_pdf_urls, other_pdf_urls)."""
    page_links, syllabus_pdfs, other_pdfs = [], [], []
    if not result.links:
        return page_links, syllabus_pdfs, other_pdfs

    source_is_course_site = urlparse(source_url).netloc == SYLLABUS_SOURCE_DOMAIN
    all_links = result.links.get("internal", []) + result.links.get("external", [])

    for link in all_links:
        href = link.get("href", "")
        if not href or not href.startswith("http"):
            continue

        # Reject malformed concatenated URLs
        if "://" in urlparse(href).path:
            continue

        if href.lower().endswith(".pdf") or "/@@download/" in href.lower():
            (syllabus_pdfs if source_is_course_site else other_pdfs).append(href)
            continue

        if any(urlparse(href).path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            continue

        if urlparse(href).netloc not in ALLOWED_DOMAINS:
            continue

        if any(x in href for x in SKIP_URL_FRAGMENTS):
            continue

        page_links.append(href.split("?")[0])

    return list(set(page_links)), list(set(syllabus_pdfs)), list(set(other_pdfs))


# ── PDF handling ──────────────────────────────────────────────────────────────

async def download_and_extract_pdf(pdf_url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        reader = PdfReader(io.BytesIO(resp.content))
        pages_text = [
            f"### Page {i}\n\n{page.extract_text().strip()}"
            for i, page in enumerate(reader.pages, 1)
            if (page.extract_text() or "").strip()
        ]
        return "\n\n".join(pages_text) if pages_text else None
    except Exception as e:
        print(f"    [PDF ERR] {pdf_url} — {e}")
        return None


async def process_syllabus_pdfs(pdf_urls: set, pdf_dir: Path):
    if not pdf_urls:
        return
    print(f"\n=== SYLLABUS PDFs ({len(pdf_urls)}) ===\n")
    ok = 0
    for pdf_url in sorted(pdf_urls):
        outpath = pdf_dir / url_to_filename(pdf_url)
        if outpath.exists():
            print(f"  [CACHED] {outpath.name}")
            ok += 1
            continue
        print(f"  Extracting: {pdf_url}")
        text = await download_and_extract_pdf(pdf_url)
        if text:
            with open(outpath, "w", encoding="utf-8") as f:
                f.write(f"# PDF Source: {pdf_url}\n\n{text}")
            print(f"    → saved ({len(text):,} chars)")
            ok += 1
        else:
            print(f"    → no extractable text")
    print(f"\nSyllabus PDFs: {ok}/{len(pdf_urls)} extracted → {pdf_dir}/")


def save_pdf_links(pdf_urls: set, output_dir: Path):
    if not pdf_urls:
        return
    ref_path = output_dir / "_pdf_references.json"
    with open(ref_path, "w", encoding="utf-8") as f:
        json.dump(sorted(pdf_urls), f, indent=2, ensure_ascii=False)
    print(f"PDF links saved: {len(pdf_urls)} → {ref_path}")


# ── Page scraping ─────────────────────────────────────────────────────────────

async def scrape_page(
    crawler: AsyncWebCrawler,
    url: str,
    syllabus_queue: set,
    pdf_link_queue: set,
    output_dir: Path,
) -> tuple[bool, list[str]]:
    shallow = is_shallow_url(url)
    filepath = output_dir / url_to_filename(url)
    try:
        result = await crawler.arun(url=url, config=TITLES_ONLY_CONFIG if shallow else CRAWLER_CONFIG)

        if not result.success:
            print(f"  [FAIL] {result.error_message}")
            return False, []

        markdown = result.markdown.raw_markdown if result.markdown else ""
        if not markdown or len(markdown.strip()) < 50:
            print(f"  [SKIP] too short ({len(markdown)} chars)")
            return False, []

        if filepath.exists():
            print(f"  [CACHED] {filepath.name} — collecting links only")
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Source: {url}\n")
                if shallow:
                    f.write("<!-- titles only -->\n")
                f.write(f"\n{markdown}")
            label = "SHALLOW" if shallow else "OK"
            print(f"  [{label}]  {filepath.name}  ({len(markdown):,} chars)")

        page_links, syllabus_pdfs, other_pdfs = collect_links(result, url)
        syllabus_queue.update(syllabus_pdfs)
        pdf_link_queue.update(other_pdfs)

        return True, ([] if shallow else page_links)

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False, []


# ── Checkpoint ────────────────────────────────────────────────────────────────

def checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "_checkpoint.json"


def save_checkpoint(visited: set, heap: list, syllabus_queue: set, pdf_link_queue: set, output_dir: Path):
    with open(checkpoint_path(output_dir), "w", encoding="utf-8") as f:
        json.dump({
            "visited": list(visited),
            "queue": heap,
            "syllabus_pdfs": list(syllabus_queue),
            "pdf_links": list(pdf_link_queue),
        }, f, ensure_ascii=False)


def load_checkpoint(output_dir: Path) -> dict | None:
    cp = checkpoint_path(output_dir)
    if cp.exists():
        with open(cp, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[RESUME] Checkpoint found: {len(data['visited'])} visited, {len(data['queue'])} queued")
        return data

    visited_urls = []
    for md_file in output_dir.glob("*.md"):
        if md_file.name.startswith("_"):
            continue
        try:
            first_line = md_file.read_text(encoding="utf-8").split("\n")[0]
            if first_line.startswith("# Source: "):
                visited_urls.append(first_line[10:].strip())
        except Exception:
            pass

    if visited_urls:
        print(f"[RESUME] No checkpoint — rebuilt {len(visited_urls)} visited URLs from existing files")
        return {"visited": visited_urls, "queue": None, "syllabus_pdfs": [], "pdf_links": []}

    return None


# ── BFS crawl ─────────────────────────────────────────────────────────────────

def _priority(url: str, depth: int) -> int:
    boosted = any(urlparse(url).path.startswith(p) for p in BOOSTED_PREFIXES)
    return depth * 2 if boosted else depth * 2 + 1


async def crawl(seed_urls: list[str], max_pages: int, output_dir: Path, pdf_dir: Path, concurrency: int):
    print(f"\n=== CRAWL (max_pages={max_pages}) ===")
    print(f"Seeds: {seed_urls}\n")

    _seq = count()
    heap: list = []

    def enqueue(url: str, depth: int):
        heapq.heappush(heap, (_priority(url, depth), next(_seq), depth, url))

    checkpoint = load_checkpoint(output_dir)
    if checkpoint and checkpoint["queue"]:
        visited: set[str] = set(checkpoint["visited"])
        syllabus_queue: set[str] = set(checkpoint["syllabus_pdfs"])
        pdf_link_queue: set[str] = set(checkpoint["pdf_links"])
        for entry in checkpoint["queue"]:
            score, _old_seq, depth, url = entry
            heapq.heappush(heap, (score, next(_seq), depth, url))
        print(f"[RESUME] Full restore: {len(visited)} visited, {len(heap)} queued\n")
    elif checkpoint:
        visited: set[str] = set(checkpoint["visited"])
        syllabus_queue: set[str] = set(checkpoint["syllabus_pdfs"])
        pdf_link_queue: set[str] = set(checkpoint["pdf_links"])
        enqueued = 0
        for base_url in seed_urls:
            if "corsi.unibo.it" not in base_url:
                continue
            for subpage in COURSE_SUBPAGES:
                url = f"{base_url.rstrip('/')}/{subpage}"
                if url not in visited:
                    enqueue(url, 1)
                    enqueued += 1
        print(f"[RESUME] Restored {len(visited)} visited URLs — {enqueued} missing sub-pages enqueued\n")
    else:
        visited: set[str] = set()
        syllabus_queue: set[str] = set()
        pdf_link_queue: set[str] = set()
        for u in seed_urls:
            enqueue(u, 0)

    log = []
    pages_since_checkpoint = 0
    visited_at_start = len(visited)

    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        while heap and (len(visited) - visited_at_start) < max_pages:
            batch = []
            while heap and len(batch) < concurrency and (len(visited) - visited_at_start) < max_pages:
                score, _, depth, url = heapq.heappop(heap)
                if url in visited:
                    continue
                visited.add(url)
                batch.append((score, depth, url))

            if not batch:
                continue

            results = await asyncio.gather(
                *[scrape_page(crawler, url, syllabus_queue, pdf_link_queue, output_dir)
                  for _, _, url in batch]
            )

            for (score, depth, url), (ok, children) in zip(batch, results):
                tag = "*" if score == depth * 2 else " "
                new_count = len(visited) - visited_at_start
                print(f"[{new_count}/{max_pages}] d={depth}{tag} {url}")
                log.append({"url": url, "status": "ok" if ok else "skip", "depth": depth})
                for child in children:
                    if child not in visited:
                        enqueue(child, depth + 1)

            pages_since_checkpoint += len(batch)
            if pages_since_checkpoint >= CHECKPOINT_INTERVAL:
                save_checkpoint(visited, heap, syllabus_queue, pdf_link_queue, output_dir)
                pages_since_checkpoint = 0

    save_checkpoint(visited, heap, syllabus_queue, pdf_link_queue, output_dir)
    with open(output_dir / "_crawl_summary.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    ok_count = sum(1 for r in log if r["status"] == "ok")
    print(f"\nPages: {ok_count}/{len(log)} saved → {output_dir}/")

    await process_syllabus_pdfs(syllabus_queue, pdf_dir)
    save_pdf_links(pdf_link_queue, output_dir)

    failed = [r["url"] for r in log if r["status"] == "skip"]
    if failed:
        print(f"\n=== RETRY {len(failed)} FAILED PAGES ===\n")
        retry_ok = 0
        async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
            for url in failed:
                print(f"  Retrying: {url}")
                ok, _ = await scrape_page(crawler, url, syllabus_queue, pdf_link_queue, output_dir)
                if ok:
                    retry_ok += 1
        print(f"\nRetry: {retry_ok}/{len(failed)} recovered")
        await process_syllabus_pdfs(syllabus_queue, pdf_dir)
        save_pdf_links(pdf_link_queue, output_dir)


# ── Retry mode ────────────────────────────────────────────────────────────────

async def retry_failed(output_dir: Path, pdf_dir: Path):
    summary_path = output_dir / "_crawl_summary.json"
    if not summary_path.exists():
        print("No _crawl_summary.json found.")
        return

    with open(summary_path, encoding="utf-8") as f:
        log = json.load(f)

    failed = [r["url"] for r in log if r["status"] == "skip"]
    if not failed:
        print("No failed pages to retry.")
        return

    print(f"\n=== RETRY {len(failed)} FAILED PAGES ===\n")
    syllabus_queue: set[str] = set()
    pdf_link_queue: set[str] = set()
    retry_ok = 0

    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        for i, url in enumerate(failed, 1):
            print(f"[{i}/{len(failed)}] {url}")
            ok, _ = await scrape_page(crawler, url, syllabus_queue, pdf_link_queue, output_dir)
            if ok:
                retry_ok += 1
                for r in log:
                    if r["url"] == url:
                        r["status"] = "ok"
                        break

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"\nRetry: {retry_ok}/{len(failed)} recovered")
    await process_syllabus_pdfs(syllabus_queue, pdf_dir)
    save_pdf_links(pdf_link_queue, output_dir)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    preset_names = ", ".join(PRESET_URLS.keys())
    parser = argparse.ArgumentParser(
        description="BFS web scraper for the University of Bologna website.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python scraper.py
  python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence
  python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence \\
                    --url https://www.unibo.it/en/homepage --max-pages 300
  python scraper.py --url-file my_courses.txt --max-pages 500
  python scraper.py --preset ai-msc --max-pages 300
  python scraper.py --retry

Available presets: {preset_names}
        """,
    )
    parser.add_argument(
        "--url", action="append", dest="urls", metavar="URL",
        help="Seed URL to start crawling from (can be repeated).",
    )
    parser.add_argument(
        "--url-file", metavar="FILE",
        help="Path to a text file with seed URLs, one per line (# lines are ignored).",
    )
    parser.add_argument(
        "--preset", choices=list(PRESET_URLS.keys()), metavar="NAME",
        help=f"Use a predefined set of course seed URLs. Choices: {preset_names}.",
    )
    parser.add_argument(
        "--max-pages", type=int, default=5000, metavar="N",
        help="Maximum number of NEW pages to crawl per run (default: 5000).",
    )
    parser.add_argument(
        "--output-dir", default="output_markdown", metavar="DIR",
        help="Directory for saved markdown files (default: output_markdown).",
    )
    parser.add_argument(
        "--pdf-dir", default="output_pdf", metavar="DIR",
        help="Directory for extracted PDF text files (default: output_pdf).",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, metavar="N",
        help="Number of pages crawled in parallel (default: 5).",
    )
    parser.add_argument(
        "--retry", action="store_true",
        help="Retry previously failed pages from _crawl_summary.json.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    output_dir = Path(args.output_dir)
    pdf_dir = Path(args.pdf_dir)
    output_dir.mkdir(exist_ok=True)
    pdf_dir.mkdir(exist_ok=True)

    if args.retry:
        asyncio.run(retry_failed(output_dir, pdf_dir))
    else:
        # URL priority: --url > --url-file > --preset > built-in defaults
        seed_urls: list[str] = []

        if args.urls:
            seed_urls.extend(args.urls)

        if args.url_file:
            url_file = Path(args.url_file)
            if not url_file.exists():
                print(f"[ERROR] --url-file not found: {url_file}")
                raise SystemExit(1)
            file_urls = [
                line.strip()
                for line in url_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            print(f"[URL-FILE] Loaded {len(file_urls)} URLs from {url_file}")
            seed_urls.extend(file_urls)

        if args.preset:
            preset_urls = PRESET_URLS[args.preset]
            print(f"[PRESET] '{args.preset}': {len(preset_urls)} seed URLs")
            seed_urls.extend(preset_urls)

        if not seed_urls:
            seed_urls = DEFAULT_SEED_URLS

        # Deduplicate while preserving order
        seen: set[str] = set()
        seed_urls = [u for u in seed_urls if not (u in seen or seen.add(u))]

        asyncio.run(crawl(seed_urls, args.max_pages, output_dir, pdf_dir, args.concurrency))
