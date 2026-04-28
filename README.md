# Unibo Scraper

A BFS web scraper for the University of Bologna website
(`unibo.it`, `corsi.unibo.it`, `eng.unibo.it`).
Crawls English-only pages, converts HTML to Markdown, and extracts text from course PDFs.

## Installation

```bash
pip install -r requirements.txt
crawl4ai-setup    # installs Playwright browsers (run once)
```

## Quick Start

```bash
# Single course
python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence

# Predefined course preset
python scraper.py --preset ai-msc --max-pages 300

# Multiple seeds from a file
python scraper.py --url-file my_courses.txt --max-pages 500

# Clean the output
python clean.py
```

Seed URLs are picked from the first source provided, in order:
`--url` → `--url-file` → `--preset` → built-in defaults.

## Scraper Options

| Option | Default | Description |
| --- | --- | --- |
| `--url URL` | — | Seed URL (repeatable) |
| `--url-file FILE` | — | Text file with one URL per line (`#` for comments) |
| `--preset NAME` | — | Course preset: `ai-msc`, `cs-msc`, `data-science`, `robotics` |
| `--max-pages N` | `5000` | Max new pages per run |
| `--output-dir DIR` | `output_markdown` | Markdown output |
| `--pdf-dir DIR` | `output_pdf` | Extracted PDF text output |
| `--concurrency N` | `5` | Parallel requests |
| `--retry` | — | Retry failed pages from the previous run |

## Cleaner Options (`clean.py`)

| Option | Default | Description |
| --- | --- | --- |
| `--input-dir DIR` | `output_markdown` | Raw markdown input |
| `--output-dir DIR` | `output_cleaned` | Cleaned output |
| `--min-chars N` | `200` | Drop files shorter than this |

## Output

```
output_markdown/      # raw crawled pages (one .md per URL)
  _checkpoint.json    # BFS state for resuming
  _crawl_summary.json # per-URL crawl log
  _pdf_references.json
output_pdf/           # extracted PDF text
output_cleaned/       # cleaned markdown (from clean.py)
cleaning_report.json  # cleaning stats
```

## Resuming

A checkpoint is saved every 20 pages.
Re-running the same command continues from where it stopped.
To start fresh, delete `output_markdown/_checkpoint.json`.

## Notes

- Only `unibo.it`, `corsi.unibo.it`, and `eng.unibo.it` are crawled.
- News, events, and notice-board pages are saved as titles only.
