#!/usr/bin/env python3
"""Download every NFL Game Book PDF for a week and extract its text.

    python3 fetch_week.py 7
    python3 fetch_week.py 7 --season 2026 --outdir gamebooks/week07

Steps, all automatic:
  1. Fetch the league schedule page for the week and read off every game slug.
  2. Fetch each game page and pull its Game Book PDF link out of the HTML.
  3. Download each PDF and extract it to fixed-layout text with pdftotext.

Games with no Game Book link yet are reported as PENDING -- the PDF is
published some time after a game goes final, so a week pulled too early will
simply be missing those games. Re-run later to collect them; existing files
are skipped unless --force is given.

Network note: this reaches www.nfl.com and static.www.nfl.com directly from
the shell. Both must be allowed under Settings > Capabilities on claude.ai.
If downloads fail with a 403 CONNECT error, that allowance is missing.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

SCHEDULE = "https://www.nfl.com/schedules/{season}/by-week/week-{week}"
GAME = "https://www.nfl.com{slug}"
PDF_RE = re.compile(
    r"https://static\.www\.nfl\.com/[^\s\"'\\]+?/gamecenter/[0-9a-f-]+\.pdf")


def curl(url, out=None, timeout=90):
    cmd = ["curl", "-sS", "-L", "--max-time", str(timeout)]
    cmd += ["-o", out] if out else []
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {r.stderr.strip()[:300]}")
    return r.stdout


def game_slugs(season, week):
    html = curl(SCHEDULE.format(season=season, week=week))
    pattern = re.compile(rf"/games/[a-z0-9-]+-{season}-reg-{week}\b")
    return sorted(set(pattern.findall(html)))


def gamebook_url(slug):
    """The PDF link, or None when the Game Book is not published yet."""
    html = curl(GAME.format(slug=slug))
    found = PDF_RE.findall(html)
    return found[0] if found else None


def slug_nicknames(name):
    """'bengals-at-commanders' -> ('bengals', 'commanders')."""
    parts = name.split("-at-")
    return (parts[0], parts[1]) if len(parts) == 2 else (None, None)


def book_names_teams(head_text, name):
    """Does this Game Book's header name both teams the slug names?

    A game page carries a Game Book link for every game of the week, not only
    its own, and the page's FIRST link is this game's book only once that book
    has been published. Until then the first link belongs to some other game,
    so an unchecked download files another game's statistics under this game's
    name. It fails silently, and only on a week pulled before every game has
    finished -- exactly the partial pull of SESSION_INSTRUCTIONS section 4.
    Week 11 was pulled on the Sunday evening: the pages for the two games still
    in progress both served the Thursday Colts-Texans book.
    """
    vis, home = slug_nicknames(name)
    if not vis:
        return True
    head = head_text.lower()
    return vis in head and home in head


def book_matches(txt_path, name):
    """book_names_teams against the top of an extracted Game Book."""
    with open(txt_path, encoding="utf-8", errors="replace") as fh:
        head = "".join(fh.readline() for _ in range(8))
    return book_names_teams(head, name)


def extract_text(pdf_path, txt_path):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not installed (apt-get install poppler-utils)")
    subprocess.run(["pdftotext", "-layout", pdf_path, txt_path], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("week", type=int)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--outdir")
    ap.add_argument("--force", action="store_true",
                    help="re-download games already present")
    args = ap.parse_args()

    outdir = args.outdir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "gamebooks", f"week{args.week:02d}")
    os.makedirs(outdir, exist_ok=True)

    slugs = game_slugs(args.season, args.week)
    if not slugs:
        sys.exit(f"No games found for {args.season} week {args.week}. "
                 "Check the season and week number.")

    print(f"{len(slugs)} games in week {args.week}\n")
    got, pending, failed = [], [], []

    for slug in slugs:
        name = slug.rsplit("/", 1)[-1].replace(f"-{args.season}-reg-{args.week}", "")
        pdf = os.path.join(outdir, f"{name}.pdf")
        txt = os.path.join(outdir, f"{name}.txt")

        if os.path.exists(txt) and not args.force:
            print(f"  {name:<28} already have it")
            got.append(name)
            continue

        try:
            url = gamebook_url(slug)
        except RuntimeError as exc:
            print(f"  {name:<28} ERROR {exc}")
            failed.append(name)
            continue

        if not url:
            print(f"  {name:<28} PENDING (no Game Book yet)")
            pending.append(name)
            continue

        try:
            curl(url, out=pdf)
            extract_text(pdf, txt)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"  {name:<28} ERROR {exc}")
            failed.append(name)
            continue

        if not book_matches(txt, name):
            os.remove(pdf)
            os.remove(txt)
            print(f"  {name:<28} PENDING (page served another game's book)")
            pending.append(name)
            continue

        print(f"  {name:<28} {os.path.getsize(pdf)//1024} KB")
        got.append(name)

    print(f"\n{len(got)} downloaded, {len(pending)} pending, {len(failed)} failed")
    print(f"text in {outdir}/")
    if pending:
        print("\nRe-run after those games finish; existing files are skipped.")


if __name__ == "__main__":
    main()
