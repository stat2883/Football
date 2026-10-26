#!/usr/bin/env python3
"""Download a season's regular-season schedule and save it to the repo.

    python3 fetch_schedule.py                 # -> schedule-2026.csv
    python3 fetch_schedule.py --season 2027

Writes `week,visitor,home` for every regular-season game, one row per
game, sorted by week. `parse_week.py` reads it to tell a bye from a game
that simply has not been pulled yet -- two situations that look
identical from the gamebooks directory, and that must not be confused:
a bye is excluded from a player's games played, while a game not yet
pulled must leave him without a row at all so the week can be topped up
later.

The schedule is fixed once the season is announced, so this is run once
and committed. The weekly pipeline then needs no network beyond
fetch_week.py itself.

Team names are written in full ("Las Vegas Raiders") to match the `team`
column in players.csv. The schedule pages give only nicknames, so the
full names are recovered from the Game Books already downloaded; any
nickname that cannot be resolved is reported rather than guessed.

Needs www.nfl.com allowed under Settings > Capabilities on claude.ai,
the same as fetch_week.py.
"""

import argparse
import csv
import glob
import os
import re
import sys

from fetch_week import curl

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE = "https://www.nfl.com/schedules/{season}/by-week/week-{week}"

# Nicknames whose full name is not simply the last word, should the
# league ever field one. Checked before the last-word rule.
SPECIAL = {}


def team_names_from_gamebooks(root):
    """nickname -> full team name, read from any Game Books on disk."""
    header = re.compile(
        r"Date:\s+\w+,\s+\d+/\d+/\d+\s+(.+?)\s+at\s+(.+?)\s+Start Time:")
    names = set()
    for path in glob.glob(os.path.join(root, "gamebooks", "week*", "*.txt")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ln in list(fh)[:12]:
                m = header.search(ln)
                if m:
                    names.add(m.group(1).strip())
                    names.add(m.group(2).strip())
                    break
    mapping = dict(SPECIAL)
    for full in names:
        mapping.setdefault(full.split()[-1].lower(), full)
    return mapping


def week_games(season, week):
    """[(visitor_nick, home_nick), ...] for one week, in schedule order."""
    html = curl(SCHEDULE.format(season=season, week=week))
    pat = re.compile(rf"/games/([a-z0-9-]+)-{season}-reg-{week}\b")
    seen, out = set(), []
    for base in pat.findall(html):
        if base in seen or "-at-" not in base:
            continue
        seen.add(base)
        vis, home = base.split("-at-", 1)
        out.append((vis, home))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--weeks", type=int, default=18)
    ap.add_argument("--out")
    args = ap.parse_args()

    out = args.out or os.path.join(HERE, f"schedule-{args.season}.csv")
    names = team_names_from_gamebooks(HERE)
    if not names:
        sys.exit("No Game Books on disk to read team names from. "
                 "Run fetch_week.py for at least one week first.")

    rows, unknown = [], set()
    for wk in range(1, args.weeks + 1):
        games = week_games(args.season, wk)
        if not games:
            print(f"  week {wk:>2}  no games found", file=sys.stderr)
            continue
        playing = set()
        for vis, home in games:
            for nick in (vis, home):
                if nick not in names:
                    unknown.add(nick)
            playing |= {vis, home}
            rows.append({"week": wk,
                         "visitor": names.get(vis, vis),
                         "home": names.get(home, home)})
        byes = sorted(set(names) - playing)
        print(f"  week {wk:>2}  {len(games):>2} games"
              + (f"   bye: {', '.join(names[b] for b in byes)}" if byes else ""))

    if unknown:
        sys.exit("\nCould not resolve these nicknames to full team names: "
                 + ", ".join(sorted(unknown))
                 + "\nDownload a Game Book for each and re-run; they are not guessed.")

    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["week", "visitor", "home"])
        w.writeheader()
        w.writerows(rows)

    teams = {r["visitor"] for r in rows} | {r["home"] for r in rows}
    print(f"\n{len(rows)} games across {args.weeks} weeks -> "
          f"{os.path.relpath(out, HERE)}")
    print(f"{len(teams)} teams")
    per_team = {t: 0 for t in teams}
    for r in rows:
        per_team[r["visitor"]] += 1
        per_team[r["home"]] += 1
    odd = {t: n for t, n in per_team.items() if n != args.weeks - 1}
    if odd:
        print("\nTeams not playing the expected number of games:")
        for t, n in sorted(odd.items()):
            print(f"  {t:<24} {n}")
        return 1
    print(f"every team plays {args.weeks - 1} games with one bye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
