#!/usr/bin/env python3
"""Hand-checkable cases for score.py. Run: python3 -I test_scoring.py

Each case states the arithmetic in its comment so the expected number can be
verified by hand against scoring.json without reading the implementation.
"""

import sys
from score import load_rules, score_row

RULES = load_rules()
CASES = []


def case(desc, expected, **stats):
    CASES.append((desc, expected, stats))


# --- yardage resolution (0.01) -------------------------------------------
# 3 rush yds * 0.1 = 0.3
case("3 rushing yards", 0.30, name="t", position="RB", rush_yds=3)
# 3 pass yds * 0.05 = 0.15
case("3 passing yards", 0.15, name="t", position="QB", pass_yds=3)
# 87 rush yds * 0.1 = 8.7  (continuous, not floored to 8)
case("87 rushing yards is not floored", 8.70, name="t", position="RB", rush_yds=87)

# --- QB passing bonus: highest tier only ----------------------------------
# 410 * 0.05 = 20.5, + 7 (400 tier only, NOT 5+7) = 27.5
case("410 pass yds takes the 400 tier only", 27.50,
     name="t", position="QB", pass_yds=410)
# 320 * 0.05 = 16.0, + 5 = 21.0
case("320 pass yds takes the 300 tier", 21.00,
     name="t", position="QB", pass_yds=320)

# --- QB passing + rushing bonuses stack -----------------------------------
# Lamar scenario: 320 pass (16.0) + 5 passing bonus
#               + 105 rush (10.5) + 5 rush bonus
#               + 2 pass TD (12) = 48.5
case("QB passing and rushing bonuses stack", 48.50,
     name="t", position="QB", pass_yds=320, rush_yds=105, pass_td=2)

# --- rush/rec group: highest only, across both stats ----------------------
# 150 rush (15.0) + 150 rec (15.0) + 6 rec (6) = 36.0
# bonuses: 100-rush(5), 100-rec(5), 100-combined(3) all qualify -> take 5
case("150/150 takes one 5-pt bonus, not three", 41.00,
     name="t", position="RB", rush_yds=150, rec_yds=150, rec=6)
# 60 rush (6.0) + 50 rec (5.0) + 4 rec (4) = 15.0, + 3 combined bonus = 18.0
case("60 rush + 50 rec earns only the combined bonus", 18.00,
     name="t", position="WR", rush_yds=60, rec_yds=50, rec=4)
# 205 rush (20.5) + 7 (200 tier) = 27.5
case("205 rushing takes the 200 tier", 27.50,
     name="t", position="RB", rush_yds=205)

# --- receiving TD exists (the corrected rule) -----------------------------
# 5 rec (5) + 70 yds (7.0) + 1 rec TD (6) = 18.0
case("receiving TD scores 6", 18.00,
     name="t", position="WR", rec=5, rec_yds=70, rec_td=1)

# --- 50+ yard TD bonus pays both players ----------------------------------
# QB: 300 pass yds (15.0) + 5 bonus + 1 pass TD (6) + 6 long = 32.0
case("QB credited on a 55-yd TD pass", 32.00,
     name="t", position="QB", pass_yds=300, pass_td=1, td_50plus=1)
# WR: 3 rec (3) + 55 yds (5.5) + 1 TD (6) + 6 long = 20.5
case("WR credited on the same 55-yd TD pass", 20.50,
     name="t", position="WR", rec=3, rec_yds=55, rec_td=1, td_50plus=1)

# --- interceptions thrown --------------------------------------------------
# 250 * 0.05 = 12.5, 2 INT * -2 = -4 -> 8.5
case("two interceptions thrown", 8.50,
     name="t", position="QB", pass_yds=250, int_thrown=2)

# --- two-point conversions pay both players -------------------------------
case("QB 2pt pass", 2.00, name="t", position="QB", pass_2pt=1)
case("WR 2pt reception", 2.00, name="t", position="WR", rec_2pt=1)

# --- kicking ---------------------------------------------------------------
# 2*3 + 1*5 + 1*7 + 1*10 + 3*2 = 6+5+7+10+6 = 34
case("full kicker line", 34.00, name="t", position="K",
     fg_0_39=2, fg_40_49=1, fg_50_59=1, fg_60plus=1, xp_made=3)

# --- defense ---------------------------------------------------------------
# 60-yd pick six: 6 (def TD) + 6 (50+) + 6.0 (60 ret yds) = 18.0
case("60-yard pick six stacks to 18", 18.00,
     name="t", position="DEF", def_td=1, def_td_50plus=1,
     def_int_ret_yds=60, pts_allowed=21)
# shutout: 15
case("shutout tier", 15.00, name="t", position="DEF", pts_allowed=0)
# 21 allowed -> 0 from that parameter; 3 sacks (9) + 1 INT (3) = 12
case("21 points allowed scores 0 for that parameter", 12.00,
     name="t", position="DEF", def_sack=3, def_int=1, pts_allowed=21)
# 20 allowed -> 3
case("20 points allowed takes the 14-20 tier", 3.00,
     name="t", position="DEF", pts_allowed=20)
# fumble returned for TD, 30 yds: 6 (TD) + 3.0 (yards) + 3 (recovery) = 12.0
case("fumble return TD counts its yards", 12.00,
     name="t", position="DEF", def_td=1, def_fum_rec=1,
     def_fum_ret_td_yds=30, pts_allowed=21)
# fumble recovered, returned, no TD -> yards ignored, just the 3-pt recovery
case("fumble recovery without a TD ignores return yards", 3.00,
     name="t", position="DEF", def_fum_rec=1, pts_allowed=21)

# --- special teams return TD goes to the returner, not the defense ---------
case("returner gets 6 for a kick return TD", 6.00,
     name="t", position="WR", st_ret_td=1)


# --- status column is inert ------------------------------------------------
# A labelled bye week scores 0 and does not raise.
case("BYE status scores zero without error", 0.00,
     name="t", position="RB", status="BYE")
# Status never affects arithmetic. 85 rush yds * 0.1 = 8.5, no bonus tier.
case("status does not alter scoring", 8.50,
     name="t", position="RB", status="DNP", rush_yds=85)


def test_text_in_numeric_column_is_caught():
    """A label in a numeric column must fail loudly, not score as zero."""
    row = {"name": "t", "position": "RB", "team": "TST", "rush_yds": "BYE"}
    try:
        score_row(row, RULES)
    except ValueError as exc:
        return "rush_yds" in str(exc)
    return False


def run():
    failures = []
    for desc, expected, stats in CASES:
        row = {k: str(v) for k, v in stats.items()}
        row.setdefault("team", "TST")
        got, lines = score_row(row, RULES)
        if abs(got - expected) > 1e-9:
            failures.append((desc, expected, got, lines))

    for desc, expected, got, lines in failures:
        print(f"FAIL  {desc}\n      expected {expected:.2f}, got {got:.2f}")
        for label, pts in lines:
            print(f"        {label:<34} {pts:>8.2f}")

    guard_ok = test_text_in_numeric_column_is_caught()
    if not guard_ok:
        print("FAIL  text in a numeric column was not rejected")

    passed = len(CASES) - len(failures) + (1 if guard_ok else 0)
    print(f"\n{passed}/{len(CASES) + 1} cases passed")
    return 1 if (failures or not guard_ok) else 0


if __name__ == "__main__":
    sys.exit(run())
