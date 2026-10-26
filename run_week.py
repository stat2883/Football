#!/usr/bin/env python3
"""Split and score one week of raw stats into per-position weekly files.

    python3 run_week.py 6 weeks/raw-week06.csv

Writes QB/Week06-QB.csv, RB/Week06-RB.csv, ... one file per position,
containing that position's stat columns plus a trailing points column.

Input is the full flat schema (weeks/_TEMPLATE.csv). Columns a position
doesn't use are dropped on the way out, so a QB file carries no kicking
columns. The raw stats are preserved in the output, which is what makes a
later scoring-rule change re-runnable without re-pulling anything.
"""

import argparse
import csv
import os

from positions import POSITIONS, SCHEMAS, display_name, sort_key, split_name
from score import load_rules, score_row

HERE = os.path.dirname(os.path.abspath(__file__))


def load_roster(path=None):
    path = path or os.path.join(HERE, "players.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["name"]: r for r in csv.DictReader(fh)}


def week_tag(week):
    return f"Week{int(week):02d}"


def run(week, stats_csv, rules, roster, outdir=HERE):
    with open(stats_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    unknown = [r["name"] for r in rows if r["name"] not in roster]
    by_position = {p: [] for p in POSITIONS}

    # A row exists only once that player's game has been pulled, and every
    # pulled row must carry a status. That is what lets a partial week be
    # topped up later: no row means not yet pulled, and a blank status would
    # be ambiguous between "played normally" and "not pulled".
    blank_status = [r["name"] for r in rows if not (r.get("status") or "").strip()]
    if blank_status:
        raise ValueError(
            f"{len(blank_status)} row(s) have a blank status: "
            f"{', '.join(blank_status[:8])}"
            f"{' ...' if len(blank_status) > 8 else ''}. "
            "Use 'active' for a played game, or BYE/DNP/IR. A row with no "
            "status cannot be told apart from a game not yet pulled."
        )

    for row in rows:
        pos = (row.get("position") or "").strip().upper()
        if pos not in by_position:
            raise ValueError(f"{row.get('name')}: unknown position {pos!r}")

        total, _ = score_row(row, rules)
        ref = roster.get(row["name"], {})
        last = ref.get("last_name") or split_name(row["name"])[0]
        first = ref.get("first_name") if ref else split_name(row["name"])[1]

        out = {
            "name": display_name(last, first),
            "team": row.get("team", ""),
            "status": (row.get("status") or "").strip(),
            "last_name": last,
            "first_name": first,
        }
        for col in SCHEMAS[pos]:
            out[col] = (row.get(col) or "").strip()
        out["points"] = f"{total:.2f}"
        by_position[pos].append(out)

    written = []
    for pos in POSITIONS:
        entries = sorted(by_position[pos], key=sort_key)
        if not entries:
            continue
        os.makedirs(os.path.join(outdir, pos), exist_ok=True)
        path = os.path.join(outdir, pos, f"{week_tag(week)}-{pos}.csv")
        fields = ["name", "team", "status"] + SCHEMAS[pos] + ["points"]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(entries)
        written.append((path, len(entries)))

    pulled = {r["name"] for r in rows}
    pending = {}
    for name, ref in roster.items():
        if name not in pulled:
            pending.setdefault(ref["position"], []).append(name)

    return written, unknown, pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("week", type=int, help="week number, e.g. 6")
    ap.add_argument("stats_csv", help="raw stats for the week (flat schema)")
    ap.add_argument("--rules")
    ap.add_argument("--roster")
    args = ap.parse_args()

    written, unknown, pending = run(args.week, args.stats_csv,
                                    load_rules(args.rules),
                                    load_roster(args.roster))

    for path, n in written:
        print(f"  {os.path.relpath(path, HERE):<28} {n:>3} players")
    if unknown:
        print(f"\nNOT in players.csv ({len(unknown)}): {', '.join(unknown)}")

    if pending:
        total = sum(len(v) for v in pending.values())
        print(f"\nSTILL TO PULL for week {args.week} ({total} players):")
        for pos in POSITIONS:
            names = sorted(pending.get(pos, []))
            if names:
                print(f"  {pos:<4} {len(names):>3}  {', '.join(names)}")
        print("\nRe-run this command after adding their rows; the week's files "
              "are rebuilt from the raw file each time.")
    else:
        print(f"\nWeek {args.week} complete — every player in players.csv "
              "has a row.")


if __name__ == "__main__":
    main()
