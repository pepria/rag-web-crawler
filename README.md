# Unibo Scraper

A BFS web scraper for the University of Bologna website ([unibo.it](https://www.unibo.it) and [corsi.unibo.it](https://corsi.unibo.it)).  
Converts HTML pages to Markdown and extracts text from course-linked PDFs.

## Features

- BFS crawl starting from any URL on `www.unibo.it`, `corsi.unibo.it`, or `www.eng.unibo.it`
- English-only pages (Italian paths are skipped automatically)
- PDF text extraction for course documents and syllabi
- Resumable: saves a checkpoint every 20 pages so crawls can be interrupted and continued
- Data cleaning pipeline to remove junk pages, boilerplate, and duplicates

## Installation

```bash
pip install -r requirements.txt
crawl4ai-setup        # installs Playwright browsers (run once)
```

## Quick Start

Scrape a single course:
```bash
python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence
```

Scrape multiple courses:
```bash
python scraper.py \
  --url https://corsi.unibo.it/2cycle/artificial-intelligence \
  --url https://corsi.unibo.it/2cycle/ComputerScience \
  --max-pages 300
```

Use built-in default seeds (main unibo homepage + a few courses):
```bash
python scraper.py --max-pages 1000
```

Then clean the output:
```bash
python clean.py
```

## Scraper Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url URL` | built-in seeds | Seed URL to start from (repeatable) |
| `--max-pages N` | `5000` | Max new pages to crawl per run |
| `--output-dir DIR` | `output_markdown` | Where to save markdown files |
| `--pdf-dir DIR` | `output_pdf` | Where to save extracted PDF text |
| `--concurrency N` | `5` | Parallel requests |
| `--retry` | — | Retry failed pages from previous run |

## Cleaner Options

| Option | Default | Description |
|--------|---------|-------------|
| `--input-dir DIR` | `output_markdown` | Raw markdown input directory |
| `--output-dir DIR` | `output_cleaned` | Cleaned output directory |
| `--min-chars N` | `200` | Minimum character count to keep a file |

## Output Structure

```
output_markdown/        # raw crawled pages (one .md per URL)
  _checkpoint.json      # BFS state for resuming
  _crawl_summary.json   # per-URL crawl log
  _pdf_references.json  # non-syllabus PDF URLs found

output_pdf/             # extracted text from course PDFs

output_cleaned/         # cleaned and deduplicated markdown (run clean.py)

cleaning_report.json    # statistics from the cleaning pipeline
```

## Resuming a Crawl

The scraper saves a checkpoint every 20 pages.  
Just re-run the same command to continue from where it left off:

```bash
python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence --max-pages 500
# interrupted... re-run to continue:
python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence --max-pages 500
```

To start fresh, delete `output_markdown/_checkpoint.json`.

## Notes

- Only pages within `www.unibo.it`, `corsi.unibo.it`, and `www.eng.unibo.it` are crawled.
- News, events, and notice-board pages are saved as titles only (links are not followed).
- On Windows, ensure long path support is enabled or keep output directory paths short.
