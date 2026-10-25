#!/usr/bin/env python3
"""Apply scoring.json to a week's raw stat lines.

Usage:
    python3 score.py weeks/2026-w08.csv
    python3 score.py weeks/2026-w08.csv -o scored/2026-w08.csv
    python3 score.py weeks/2026-w08.csv --explain "Lamar Jackson"

Design note: all rule values live in scoring.json. Nothing in this file
hard-codes a point value, so a mid-season rule change means editing the
JSON only, and every week can be re-scored from the untouched raw stats.
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Raw stat columns. Anything blank or missing is treated as 0.
STAT_COLUMNS = [
    # passing
    "pass_yds", "pass_td", "pass_2pt", "int_thrown",
    # rushing
    "rush_yds", "rush_td", "rush_2pt",
    # receiving
    "rec", "rec_yds", "rec_td", "rec_2pt",
    # long/special
    "td_50plus", "st_ret_td",
    # kicking
    "fg_0_39", "fg_40_49", "fg_50_59", "fg_60plus", "xp_made",
    # defense / special teams unit
    "def_int", "def_sack", "def_fum_rec", "def_safety", "def_td",
    "def_int_ret_yds", "def_fum_ret_td_yds", "def_td_50plus", "pts_allowed",
]

IDENTITY_COLUMNS = ["name", "position", "team"]

# Optional. Free text for the human reading the file: blank or "active" for a
# normal week, otherwise BYE / DNP / IR / INACTIVE. Never used in arithmetic —
# it exists precisely so those labels stay out of the numeric columns.
STATUS_COLUMN = "status"


def load_rules(path=None):
    path = path or os.path.join(HERE, "scoring.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def num(row, key):
    """Blank, missing, or unparseable -> 0."""
    raw = (row.get(key) or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{row.get('name', '?')}: column {key!r} is not a number: {raw!r}")


def best_tier(tiers, values):
    """Highest-only: return (points, label) for the single best qualifying tier."""
    best = (0.0, None)
    for tier in tiers:
        val = values.get(tier["stat"], 0.0)
        if val >= tier["min"] and tier["points"] > best[0]:
            best = (float(tier["points"]), f"{tier['stat']} >= {tier['min']}")
    return best


def tier_for(tiers, value):
    """First tier whose [min, max] contains value. max of None means open-ended."""
    for tier in tiers:
        lo, hi = tier["min"], tier["max"]
        if value >= lo and (hi is None or value <= hi):
            return float(tier["points"])
    return 0.0


def score_row(row, rules):
    """Return (total, [(label, points), ...]) for one stat line."""
    lines = []

    def add(label, pts):
        if pts:
            lines.append((label, round(float(pts), 4)))

    position = (row.get("position") or "").strip().upper()
    g = lambda k: num(row, k)

    per_yd = rules["per_yard"]
    td = rules["touchdowns"]
    two = rules["two_point_conversions"]
    pen = rules["penalties"]
    longtd = rules["long_td_bonus"]

    if position == "DEF":
        d = rules["defense"]
        add("interceptions", g("def_int") * d["interception"])
        add("sacks", g("def_sack") * d["sack"])
        add("fumble recoveries", g("def_fum_rec") * d["fumble_recovery"])
        add("safeties", g("def_safety") * d["safety"])
        add("defensive TDs", g("def_td") * td["defensive"])
        add("INT return yards", g("def_int_ret_yds") * per_yd["interception_return"])
        # Fumble return yards count only when the return ended in a touchdown.
        add("fumble return TD yards",
            g("def_fum_ret_td_yds") * per_yd["fumble_return_td_only"])
        add(f"TDs of {longtd['min_yards']}+ yards",
            g("def_td_50plus") * longtd["points"])
        add(f"points allowed ({int(g('pts_allowed'))})",
            tier_for(d["points_allowed"], g("pts_allowed")))
        total = round(sum(p for _, p in lines), 2)
        return total, lines

    # --- offensive players and kickers ---
    add("passing yards", g("pass_yds") * per_yd["passing"])
    add("rushing yards", g("rush_yds") * per_yd["rushing"])
    add("receiving yards", g("rec_yds") * per_yd["receiving"])
    add("receptions", g("rec") * rules.get("reception_points", 1))

    add("passing TDs", g("pass_td") * td["passing"])
    add("rushing TDs", g("rush_td") * td["rushing"])
    add("receiving TDs", g("rec_td") * td["receiving"])
    add("special teams return TDs", g("st_ret_td") * td["special_teams_return"])

    add("2pt (passing)", g("pass_2pt") * two["passing"])
    add("2pt (rushing)", g("rush_2pt") * two["rushing"])
    add("2pt (receiving)", g("rec_2pt") * two["receiving"])

    add("interceptions thrown", g("int_thrown") * pen["interception_thrown"])
    add(f"TDs of {longtd['min_yards']}+ yards", g("td_50plus") * longtd["points"])

    # Yardage bonuses: highest tier within each group; groups stack.
    values = {
        "pass_yds": g("pass_yds"),
        "rush_yds": g("rush_yds"),
        "rec_yds": g("rec_yds"),
        "rush_rec_combined": g("rush_yds") + g("rec_yds"),
    }
    for group, tiers in rules["yardage_bonuses"].items():
        if group.startswith("_"):
            continue
        pts, label = best_tier(tiers, values)
        if pts:
            add(f"bonus: {label}", pts)

    k = rules["kicking"]
    fg_map = {"fg_0_39": (0, 39), "fg_40_49": (40, 49),
              "fg_50_59": (50, 59), "fg_60plus": (60, None)}
    for col, (lo, _hi) in fg_map.items():
        made = g(col)
        if made:
            add(f"FGs {col.replace('fg_', '').replace('_', '-')}",
                made * tier_for(k["fg_by_distance"], lo))
    add("extra points", g("xp_made") * k["extra_point"])

    total = round(sum(p for _, p in lines), 2)
    return total, lines


def main():
    ap = argparse.ArgumentParser(description="Score a week of fantasy stats.")
    ap.add_argument("stats_csv", help="raw weekly stats CSV")
    ap.add_argument("-o", "--out", help="output CSV (default: alongside input, .scored.csv)")
    ap.add_argument("--rules", help="path to scoring.json")
    ap.add_argument("--explain", help="print a line-by-line breakdown for this player")
    args = ap.parse_args()

    rules = load_rules(args.rules)

    with open(args.stats_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        sys.exit(f"{args.stats_csv} has no data rows.")

    missing = [c for c in IDENTITY_COLUMNS if c not in rows[0]]
    if missing:
        sys.exit(f"{args.stats_csv} is missing required column(s): {', '.join(missing)}")

    results = []
    for row in rows:
        total, lines = score_row(row, rules)
        results.append({
            "name": row["name"],
            "position": row["position"],
            "team": row["team"],
            "status": (row.get(STATUS_COLUMN) or "").strip(),
            "points": f"{total:.2f}",
        })
        if args.explain and row["name"].lower() == args.explain.lower():
            print(f"\n{row['name']} ({row['position']}, {row['team']})")
            print("-" * 48)
            for label, pts in lines:
                print(f"  {label:<36} {pts:>8.2f}")
            print("-" * 48)
            print(f"  {'TOTAL':<36} {total:>8.2f}\n")

    out = args.out or os.path.splitext(args.stats_csv)[0] + ".scored.csv"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["name", "position", "team", "status", "points"])
        w.writeheader()
        w.writerows(results)

    print(f"Scored {len(results)} players -> {out}")


if __name__ == "__main__":
    main()
