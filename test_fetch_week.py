#!/usr/bin/env python3
"""Tests for fetch_week.py, one per trap it exists to avoid.

Run: python3 test_fetch_week.py

Every case is a real string seen in a 2026 Game Book or NFL.com slug, named
with the week it came from. No network and no gamebooks/ directory needed.
"""

import sys

from fetch_week import book_names_teams, slug_nicknames

FAILS = []
CHECKS = 0


def check(desc, expected, got):
    global CHECKS
    CHECKS += 1
    if got != expected:
        FAILS.append(f"{desc}: expected {expected!r}, got {got!r}")


# A real header, trimmed to the lines book_matches reads.
def header(matchup, date="Sunday, 11/22/2026"):
    return (
        "                     National Football League Game Summary\n"
        "NFL Copyright 2026 by The National Football League.\n"
        "coverage of the game; any other use of this material is prohibited.\n"
        "\n"
        f"Date: {date}      {matchup}      Start Time: 1:02 PM EST\n"
        "                  at Bank of America Stadium, Charlotte, NC\n"
        "                            Game Day Weather\n"
        "Game Weather: Cloudy\n"
    )


def test_slug_nicknames():
    check("visitor and home split on -at-",
          ("bengals", "commanders"), slug_nicknames("bengals-at-commanders"))
    check("a numeric nickname survives",
          ("vikings", "49ers"), slug_nicknames("vikings-at-49ers"))
    check("a slug with no -at- is not split",
          (None, None), slug_nicknames("probowl2026"))


def test_book_matches_its_slug():
    # Week 11: the eight books that were in scope all named their own game.
    check("Ravens at Panthers matches its slug", True,
          book_names_teams(header("Baltimore Ravens at Carolina Panthers"),
                           "ravens-at-panthers"))
    check("a two-word city still matches", True,
          book_names_teams(header("Tampa Bay Buccaneers at Detroit Lions"),
                           "buccaneers-at-lions"))
    check("a numeric nickname matches", True,
          book_names_teams(header("Minnesota Vikings at San Francisco 49ers"),
                           "vikings-at-49ers"))


def test_wrong_book_is_caught():
    """Week 11, pulled on the Sunday evening.

    The pages for the two games still in progress carried no book of their own,
    so the first Game Book link on each belonged to Thursday's Colts-Texans
    game. Unchecked, that lands Colts and Texans statistics under another
    game's name, and the week looks complete when it is not.
    """
    thursday = header("Indianapolis Colts at Houston Texans",
                      date="Thursday, 11/19/2026")
    check("Thursday's book is refused for Bengals at Commanders", False,
          book_names_teams(thursday, "bengals-at-commanders"))
    check("Thursday's book is refused for Vikings at 49ers", False,
          book_names_teams(thursday, "vikings-at-49ers"))
    check("Thursday's book is still accepted for its own slug", True,
          book_names_teams(thursday, "colts-at-texans"))


def test_one_right_team_is_not_enough():
    # A book naming only one of the two teams is the wrong book, not a match.
    check("only the home team present is refused", False,
          book_names_teams(header("Arizona Cardinals at Kansas City Chiefs"),
                           "saints-at-chiefs"))
    check("only the visitor present is refused", False,
          book_names_teams(header("Arizona Cardinals at Kansas City Chiefs"),
                           "cardinals-at-bears"))


def main():
    for fn in (test_slug_nicknames, test_book_matches_its_slug,
               test_wrong_book_is_caught, test_one_right_team_is_not_enough):
        fn()
    for f in FAILS:
        print("FAIL ", f)
    print(f"\n{CHECKS - len(FAILS)}/{CHECKS} checks passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
