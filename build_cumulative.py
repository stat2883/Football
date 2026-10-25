#!/usr/bin/env python3
"""Regenerate Cumulative-<POS>.csv for every position from the weekly files.

    python3 build_cumulative.py

Each cumulative file holds one row per player: name, team, position, then one
column per week that exists on disk, then three summary columns.

Rebuilt from scratch every run rather than appended to. A corrected stat in an
earlier week therefore propagates to the totals automatically, instead of
leaving a stale number nobody notices.

Summary columns:
  Total Cumulative Fantasy Points - sum over active weeks
  Average Points Per Game         - mean over ACTIVE weeks only
  Standard Deviation              - sample (n-1), blank with fewer than 2 games

Weeks the player missed carry their status label (BYE, DNP, ...) rather than a
number. Those weeks are excluded from all three summary columns, so a bye never
drags an average down. The labels are safe here because this file is only ever
written, never read back as input.
"""

import argparse
import csv
import os
import re
import statistics

from positions import POSITIONS, display_name, is_inactive

HERE = os.path.dirname(os.path.abspath(__file__))
WEEK_RE = re.compile(r"^Week(\d{2})-([A-Z]+)\.csv$")

SUMMARY = ["Total Cumulative Fantasy Points",
           "Average Points Per Game",
           "Standard Deviation"]


def weekly_files(position, root=HERE):
    """[(week_number, path), ...] sorted by week."""
    d = os.path.join(root, position)
    if not os.path.isdir(d):
        return []
    found = []
    for fn in os.listdir(d):
        m = WEEK_RE.match(fn)
        if m and m.group(2) == position:
            found.append((int(m.group(1)), os.path.join(d, fn)))
    return sorted(found)


def build(position, root=HERE):
    files = weekly_files(position, root)
    if not files:
        return None, []

    players = {}   # display name -> {"team":, "weeks": {wk: value}}
    order = []

    for wk, path in files:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = row["name"]
                if key not in players:
                    players[key] = {"team": row.get("team", ""), "weeks": {}}
                    order.append(key)
                players[key]["team"] = row.get("team", "") or players[key]["team"]
                status = (row.get("status") or "").strip()
                if is_inactive(status):
                    players[key]["weeks"][wk] = status.upper()
                else:
                    players[key]["weeks"][wk] = float(row["points"])

    week_cols = [f"Week{wk:02d}" for wk, _ in files]
    rows = []
    for key in order:
        rec = players[key]
        scored = [v for v in rec["weeks"].values() if isinstance(v, float)]

        out = {"name": key, "team": rec["team"], "position": position}
        for wk, _ in files:
            val = rec["weeks"].get(wk, "")
            out[f"Week{wk:02d}"] = f"{val:.2f}" if isinstance(val, float) else val

        out[SUMMARY[0]] = f"{sum(scored):.2f}" if scored else ""
        out[SUMMARY[1]] = f"{statistics.fmean(scored):.2f}" if scored else ""
        # Sample standard deviation is undefined for a single observation;
        # a 0 there would wrongly read as "perfectly consistent".
        out[SUMMARY[2]] = (f"{statistics.stdev(scored):.2f}"
                           if len(scored) >= 2 else "")
        rows.append(out)

    rows.sort(key=lambda r: -float(r[SUMMARY[0]] or 0))

    fields = ["name", "team", "position"] + week_cols + SUMMARY
    path = os.path.join(root, position, f"Cumulative-{position}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    return path, [wk for wk, _ in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE)
    args = ap.parse_args()

    for pos in POSITIONS:
        path, weeks = build(pos, args.root)
        if path is None:
            print(f"  {pos:<4} no weekly files yet")
        else:
            span = f"weeks {min(weeks)}-{max(weeks)}" if weeks else ""
            print(f"  {os.path.relpath(path, args.root):<32} {span}")


if __name__ == "__main__":
    main()
