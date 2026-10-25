#!/usr/bin/env python3
"""Hand-checkable tests for the cumulative summary columns.

Run: python3 test_cumulative.py

Builds a throwaway week set in a temp directory, so nothing here touches
real data.
"""

import csv
import os
import shutil
import statistics
import sys
import tempfile

from build_cumulative import build, SUMMARY
from positions import SCHEMAS

FAILS = []


def check(desc, expected, got):
    if isinstance(expected, float):
        ok = got != "" and abs(float(got) - expected) < 0.005
    else:
        ok = got == expected
    if not ok:
        FAILS.append(f"{desc}: expected {expected!r}, got {got!r}")


def write_week(root, wk, rows):
    d = os.path.join(root, "QB")
    os.makedirs(d, exist_ok=True)
    fields = ["name", "team", "status"] + SCHEMAS["QB"] + ["points"]
    with open(os.path.join(d, f"Week{wk:02d}-QB.csv"), "w",
              newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    root = tempfile.mkdtemp()
    try:
        # Steady: 20, 10, 30 across three active weeks.
        # Bye player: 20, BYE, 30 -> two games, not three.
        # One-gamer: 15 in week 1 only.
        write_week(root, 1, [
            {"name": "Steady, Sam", "team": "AAA", "points": "20.00"},
            {"name": "Bye, Bob", "team": "BBB", "points": "20.00"},
            {"name": "Once, Ollie", "team": "CCC", "points": "15.00"},
        ])
        write_week(root, 2, [
            {"name": "Steady, Sam", "team": "AAA", "points": "10.00"},
            {"name": "Bye, Bob", "team": "BBB", "status": "BYE", "points": "0.00"},
            {"name": "Once, Ollie", "team": "CCC", "status": "IR", "points": "0.00"},
        ])
        write_week(root, 3, [
            {"name": "Steady, Sam", "team": "AAA", "points": "30.00"},
            {"name": "Bye, Bob", "team": "BBB", "points": "30.00"},
            {"name": "Once, Ollie", "team": "CCC", "status": "IR", "points": "0.00"},
        ])

        path, weeks = build("QB", root)
        check("weeks discovered", [1, 2, 3], weeks)

        rows = {r["name"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}

        # Sam: 20+10+30 = 60; mean 20; sample sd of (20,10,30) = 10.0
        sam = rows["Steady, Sam"]
        check("Sam total", 60.00, sam[SUMMARY[0]])
        check("Sam average over 3 games", 20.00, sam[SUMMARY[1]])
        check("Sam sample sd", statistics.stdev([20, 10, 30]), sam[SUMMARY[2]])

        # Bob: bye week excluded entirely. 20+30 = 50 over TWO games -> 25.00,
        # not 50/3 = 16.67. This is the rule that matters most.
        bob = rows["Bye, Bob"]
        check("Bob total excludes bye", 50.00, bob[SUMMARY[0]])
        check("Bob average is over 2 games, not 3", 25.00, bob[SUMMARY[1]])
        check("Bob bye cell shows the label", "BYE", bob["Week02"])
        check("Bob sample sd over 2 games",
              statistics.stdev([20, 30]), bob[SUMMARY[2]])

        # Ollie: one active game. Sample sd undefined -> blank, never 0.
        ollie = rows["Once, Ollie"]
        check("Ollie total", 15.00, ollie[SUMMARY[0]])
        check("Ollie average over 1 game", 15.00, ollie[SUMMARY[1]])
        check("Ollie sd is blank, not zero", "", ollie[SUMMARY[2]])
        check("Ollie IR cell shows the label", "IR", ollie["Week02"])

        # Column order: identity, weeks, then the three summary columns last.
        header = list(next(csv.reader(open(path, encoding="utf-8"))))
        check("header layout",
              ["name", "team", "position", "Week01", "Week02", "Week03"] + SUMMARY,
              header)

        # Sorted by total descending.
        names = [r["name"] for r in csv.DictReader(open(path, encoding="utf-8"))]
        check("sorted by total descending",
              ["Steady, Sam", "Bye, Bob", "Once, Ollie"], names)

    finally:
        shutil.rmtree(root)

    for f in FAILS:
        print("FAIL ", f)
    print(f"\n{14 - len(FAILS)}/14 checks passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
