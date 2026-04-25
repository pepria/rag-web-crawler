"""
Data cleaning pipeline for scraped Unibo markdown files.

Reads from an input directory (default: output_markdown/),
writes cleaned files to an output directory (default: output_cleaned/).

Stages:
  1. Junk filter    — removes login pages, 404s, cookie-only pages
  2. Truncation     — cuts at first cookie action bar (removes boilerplate
                      and duplicate content blocks that follow it)
  3. Content clean  — strips residual cookie headings, copyright footers,
                      and excess blank lines
  4. Min-length     — discards files with < MIN_CHARS of useful content
  5. Deduplication  — keeps one representative per identical-body group

Usage:
  python clean.py
  python clean.py --input-dir output_markdown --output-dir output_cleaned
  python clean.py --min-chars 500
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


MIN_CHARS_DEFAULT = 200


# ── Junk detection ────────────────────────────────────────────────────────────

JUNK_SIGNALS = [
    "用户帐户",
    "使我保持登录状态",
    "Enter the University institutional credentials",
    "We can't find the page you are looking for",
    "Sorry, the requested page cannot be found",
]


def is_junk(text: str) -> str | None:
    for sig in JUNK_SIGNALS:
        if sig in text:
            return f"junk:{sig[:40]}"
    return None


# ── Boilerplate truncation ────────────────────────────────────────────────────

_COOKIE_BAR = re.compile(
    r"(?:\[Essential cookies only\]|\[Solo cookie necessari\]|"
    r"\[Accetta tutti i cookie\]|chefcookie__decline|"
    r"\[Personalizza cookie\]|\[Impostazione cookie\])",
)

_YOU_ARE_HERE = re.compile(r"You are here:")

_COOKIE_SECTION_START = re.compile(
    r"#{1,2} (?:This website uses cookies|Questo sito web utilizza i cookie)"
)


def truncate_at_boilerplate(text: str) -> str:
    m = _COOKIE_BAR.search(text)
    if m:
        heading = _COOKIE_SECTION_START.search(text)
        # Cookie banner at the top (sitoweb pages): remove banner, keep content after
        if heading and heading.start() < m.start() and heading.start() < 500:
            end_of_line = text.find("\n", m.end())
            text = text[end_of_line + 1:] if end_of_line != -1 else ""
        else:
            # Cookie banner at the bottom (regular pages): keep content before
            text = text[:m.start()]

    matches = list(_YOU_ARE_HERE.finditer(text))
    if len(matches) >= 2:
        def breadcrumb(match):
            end = text.find("\n", match.start())
            return text[match.start(): end if end != -1 else match.start() + 120]

        first_bc = breadcrumb(matches[0])
        for later in matches[1:]:
            if breadcrumb(later) == first_bc:
                text = text[:later.start()]
                break

    return text


# ── Residual cleaning ─────────────────────────────────────────────────────────

_COOKIE_HEADING = re.compile(
    r"#{1,2} (?:This website uses cookies|Questo sito web utilizza i cookie).*?"
    r"(?=\[Essential cookies only\]|\[Personalizza cookie\]|\[Impostazione cookie\]|\Z)",
    re.DOTALL,
)

_COPYRIGHT = re.compile(
    r"©Copyright\s+\d{4}.*?(?:Note legali\][^\n]*\n?|CF:\s*\d+\n?|Privacy\][^\n]*\n?)",
    re.DOTALL,
)

_MULTI_BLANK = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)


def clean_content(text: str) -> str:
    text = truncate_at_boilerplate(text)
    text = _COOKIE_HEADING.sub("", text)
    text = _COPYRIGHT.sub("", text)
    text = _TRAILING_WS.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clean scraped Unibo markdown files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clean.py
  python clean.py --input-dir output_markdown --output-dir output_cleaned
  python clean.py --min-chars 500
        """,
    )
    parser.add_argument("--input-dir",  default="output_markdown", metavar="DIR",
                        help="Directory with raw markdown files (default: output_markdown).")
    parser.add_argument("--output-dir", default="output_cleaned",  metavar="DIR",
                        help="Directory for cleaned output files (default: output_cleaned).")
    parser.add_argument("--min-chars",  type=int, default=MIN_CHARS_DEFAULT, metavar="N",
                        help=f"Minimum body length to keep a file (default: {MIN_CHARS_DEFAULT}).")
    args = parser.parse_args()

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    report     = Path("cleaning_report.json")
    output_dir.mkdir(exist_ok=True)

    md_files = sorted(f for f in input_dir.glob("*.md") if not f.name.startswith("_"))
    print(f"Input files: {len(md_files)}")

    stats = {"input": len(md_files), "removed_junk": 0,
             "removed_too_short": 0, "removed_duplicate": 0, "kept": 0}
    removal_log: list[dict] = []
    candidates: list[tuple[str, str, str]] = []

    for f in md_files:
        try:
            raw = f.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            stats["removed_junk"] += 1
            continue

        lines = raw.split("\n", 1)
        source_line = lines[0] if lines[0].startswith("# Source:") else ""
        body_raw = lines[1] if len(lines) > 1 else raw

        reason = is_junk(raw)
        if reason:
            stats["removed_junk"] += 1
            removal_log.append({"file": f.name, "reason": reason})
            continue

        body_clean = clean_content(body_raw)

        if len(body_clean.strip()) < args.min_chars:
            stats["removed_too_short"] += 1
            removal_log.append({"file": f.name, "reason": "too_short"})
            continue

        candidates.append((f.name, source_line, body_clean))

    print(f"After junk+length filter: {len(candidates)} files remain")

    hash_groups: dict[str, list] = defaultdict(list)
    for fname, src, body in candidates:
        h = hashlib.md5(body.encode()).hexdigest()
        hash_groups[h].append((fname, src, body))

    for group in hash_groups.values():
        group.sort(key=lambda x: (len(x[0]), x[0]))
        keeper_fname, keeper_src, keeper_body = group[0]

        out_path = output_dir / keeper_fname
        out_path.write_text((keeper_src + "\n\n" + keeper_body).strip() + "\n", encoding="utf-8")
        stats["kept"] += 1

        for dup_fname, _, _ in group[1:]:
            stats["removed_duplicate"] += 1
            removal_log.append({"file": dup_fname, "reason": "duplicate", "kept_as": keeper_fname})

    print("\n=== Cleaning Summary ===")
    print(f"  Input:               {stats['input']:>6}")
    print(f"  Removed (junk):      {stats['removed_junk']:>6}  (login pages, 404s)")
    print(f"  Removed (too short): {stats['removed_too_short']:>6}  (< {args.min_chars} chars)")
    print(f"  Removed (duplicate): {stats['removed_duplicate']:>6}")
    print(f"  ─────────────────────────────────")
    print(f"  Kept:                {stats['kept']:>6}  → {output_dir}/")

    stats["removal_log_count"] = len(removal_log)
    report.write_text(
        json.dumps({"stats": stats, "removed": removal_log}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nFull report → {report}")


if __name__ == "__main__":
    main()
