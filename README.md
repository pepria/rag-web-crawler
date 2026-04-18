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

Scrape a single course (including professor pages):
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

Use a predefined course preset:
```bash
python scraper.py --preset ai-msc --max-pages 300
```

Load seed URLs from a text file (one URL per line, `#` for comments):
```bash
python scraper.py --url-file my_courses.txt --max-pages 500
```

Use built-in default seeds:
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
| `--url URL` | — | Seed URL to start from (repeatable) |
| `--url-file FILE` | — | Text file with seed URLs, one per line |
| `--preset NAME` | — | Use a predefined course set (see below) |
| `--max-pages N` | `5000` | Max new pages to crawl per run |
| `--output-dir DIR` | `output_markdown` | Where to save markdown files |
| `--pdf-dir DIR` | `output_pdf` | Where to save extracted PDF text |
| `--concurrency N` | `5` | Parallel requests |
| `--retry` | — | Retry failed pages from previous run |

URL sources are merged in this priority order: `--url` > `--url-file` > `--preset` > built-in defaults.

## Available Presets

| Preset | Description |
|--------|-------------|
| `ai-msc` | AI Master's degree (corsi.unibo.it) + faculty pages |
| `cs-msc` | Computer Science Master's degree + faculty pages |
| `data-science` | Statistical Sciences / Data Science degree + faculty pages |
| `robotics` | Automotive Engineering degree + faculty pages |

Professor personal pages (`/sitoweb/`) are crawled automatically when linked from faculty pages.

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
