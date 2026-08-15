# Unibo Scraper

A BFS web scraper for the University of Bologna website
(`unibo.it`, `corsi.unibo.it`, `eng.unibo.it`).
Crawls English-only pages, converts HTML to Markdown, and extracts text from
course PDFs. `clean.py` removes boilerplate and normalises the output for RAG.

Requires **Python 3.10+**.

## Installation

```bash
pip install -r requirements.txt
crawl4ai-setup    # installs Playwright browsers (run once)
```

If `crawl4ai-setup` fails, run `playwright install chromium` instead.

## Reproducing the corpus

```bash
python scraper.py --max-pages 8000    # ~1-2 hours -> output_markdown/, output_pdf/
python clean.py                       # -> output_cleaned/
```

`output_cleaned/` is the directory that gets embedded and indexed.

Reference: the corpus used for the project contains **5,809** cleaned documents.
`unibo.it` is a live site that changes over time, so a re-crawl will differ;
anything within ~10% reproduced correctly.

## Quick start

```bash
# Single course
python scraper.py --url https://corsi.unibo.it/2cycle/artificial-intelligence

# Predefined course preset
python scraper.py --preset ai-msc --max-pages 300

# Multiple seeds from a file
python scraper.py --url-file my_courses.txt --max-pages 500

# Retry pages that failed
python scraper.py --retry
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
| `--all-pdfs` | off | Extract every PDF, not only those from `corsi.unibo.it` |
| `--restrict-prefix P` | — | Only follow links starting with `P` (repeatable) |
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

Every file starts with a `# Source: <url>` line, so any document can be traced
back to its origin page.

## Resuming

A checkpoint is saved every 20 pages.
Re-running the same command continues from where it stopped.
To start fresh, delete `output_markdown/_checkpoint.json`.

## Troubleshooting

- `TypeError: unsupported operand type(s) for |` → Python is older than 3.10.
- Many `[FAIL]` lines → re-run with `--concurrency 2`, then `python scraper.py --retry`.
- Crawl stopped early → just re-run the same command, it resumes.

## Notes

- Only `unibo.it`, `corsi.unibo.it`, and `eng.unibo.it` are crawled.
- News, events, and notice-board pages are saved as titles only.
- Link extraction is sorted, so pages are visited in the same order on every
  run and `clean.py` is fully deterministic.
