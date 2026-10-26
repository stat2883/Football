#!/usr/bin/env python3
"""Tests for parse_week.py, one per trap it exists to avoid.

Run: python3 test_parse_week.py

Every case here is a real pattern seen in a 2026 Game Book, named with
the week it came from. They are written against synthetic fragments
rather than the downloaded PDFs, so the suite runs with no network and
no gamebooks/ directory present.
"""

import sys

from parse_week import (EZ_REC, FG, PASS_TD, RET_TD, RUN_TD, TWO_PT, XP_KICK,
                        KNOWN_FORMS, abbrev_match, bare_surname, defense_row,
                        offense_row, one_col_table, override_for,
                        split_name_stats, two_col_section, build,
                        load_schedule, COLUMNS)

FAILS = []
CHECKS = 0


def check(desc, expected, got):
    global CHECKS
    CHECKS += 1
    if got != expected:
        FAILS.append(f"{desc}: expected {expected!r}, got {got!r}")


def blank_row():
    return dict.fromkeys(COLUMNS, "")


# --------------------------------------------------------------------------

def test_abbreviations():
    # Week 1, Jacksonville: two Thomases, separated by a longer initial.
    check("Bri.Thomas is Brian", True, abbrev_match("Bri.Thomas", "Brian", "Thomas"))
    check("Bry.Thomas is not Brian", False, abbrev_match("Bry.Thomas", "Brian", "Thomas"))
    # A single-letter initial must still match the same player.
    check("B.Thomas is Brian", True, abbrev_match("B.Thomas", "Brian", "Thomas"))
    # Two-word surnames and punctuated first names.
    check("A.St. Brown", True, abbrev_match("A.St. Brown", "Amon-Ra", "St. Brown"))
    check("C.Stroud from 'C.J.'", True, abbrev_match("C.Stroud", "C.J.", "Stroud"))
    # Suffixes are not part of the surname the Game Book prints.
    check("suffix stripped", "Penix", bare_surname("Penix Jr"))
    check("roman suffix stripped", "Walker", bare_surname("Walker III"))
    check("two-word surname kept", "St. Brown", bare_surname("St. Brown"))
    # Wrong surname must not match on initial alone.
    check("different surname", False, abbrev_match("B.Thompson", "Brian", "Thomas"))


def test_team_sacks_total():
    # Week 1, Kansas City: four sacks, only three credited to players,
    # the fourth on an unattributed Team Sacks line. Summing player rows
    # gives 3; the Total row gives the right answer.
    table = [
        "                     TKL   AST   COMB      SK    / YDS TFL QH IN   PD  FF  FR   TKL   AST   FF   FR   BL   TKL  AST  FF  FR",
        "N.Williams             2     1      3       1       3    1  1  0    1   0   0     0     0    0    0    0     0    0   0   0",
        "R.Thomas               1     1      2       1       5    1  1  0    0   0   0     0     0    0    0    0     0    0   0   0",
        "F.Anudike-Uzomah       1     0      1       1       1    1  0  0    0   1   0     0     0    0    0    0     0    0   0   0",
        "Team Sacks             1     0      0       1       7          0    0   0   0     0     0    0    0    0     0    0   0   0",
        "Total                 23    20     42       4      16    3  5  1    4   1   1     3     8    0    0    0     0    0   0   2",
    ]
    rows, total = one_col_table(table, 0, 20)
    check("player rows parsed", 3, len(rows))
    check("summing player rows undercounts", 3.0, sum(float(s[3]) for _, s in rows))
    check("Total row is authoritative", "4", total[3])
    check("Team Sacks line is not a player", [], [n for n, _ in rows if n == "Team Sacks"])


def test_two_column_split():
    # Week 1, Saints at Lions. Visitor left, home right, one header.
    table = [
        "PASS RECEIVING          TAR   REC    YDS    AVG     LG  TD    PASS RECEIVING          TAR   REC   YDS    AVG     LG   TD",
        "C.Olave                  13    10    182   18.2     47   0    A.St. Brown              14    10    67    6.7     19    2",
        "D.Vele                    9     7     69    9.9     31   1    S.LaPorta                 8     5    48    9.6     19    0",
        "",
    ]
    vis, home = two_col_section(table, 0, "PASS RECEIVING", 6)
    check("visitor side", ["C.Olave", "D.Vele"], [n for n, _ in vis])
    check("home side", ["A.St. Brown", "S.LaPorta"], [n for n, _ in home])
    check("home yards not taken from visitor", "67", home[0][1][2])
    check("name with spaces kept whole", ("A.St. Brown", "14"),
          (home[0][0], home[0][1][0]))


def test_negative_and_zero_lines():
    # Week 2, D.J. Moore: one carry for -1 and no receptions at all.
    name, stats = split_name_stats("D.Moore     1     -1   -1.0     -1    0", 5)
    check("negative rushing parsed", ("D.Moore", "-1"), (name, stats[1]))
    # A targeted receiver with no catch still has a row.
    name, stats = split_name_stats("I.TeSlaa    1      0      0    0.0      0    0", 6)
    check("zero-catch receiver", ("I.TeSlaa", "0"), (name, stats[1]))


def test_scoring_play_forms():
    # Week 3, San Francisco: a lateral reads "pass play by", and the
    # Game Book still credits the quarterback with the touchdown.
    m = PASS_TD.match("D.Samuel 82 yd. pass play by B.Purdy (E.Pineiro kick) (3-80, 0:52)")
    check("lateral wording recognised", True, m is not None)
    check("lateral scorer", "D.Samuel", m.group(1))
    check("lateral yardage", "82", m.group(2))
    check("lateral passer credited", "B.Purdy", m.group(3))

    m = PASS_TD.match("A.St. Brown 19 yd. pass from J.Goff (J.Bates kick) (3-25, 0:51)")
    check("ordinary pass wording", ("A.St. Brown", "19", "J.Goff"),
          (m.group(1), m.group(2), m.group(3)))

    m = RUN_TD.match("K.Monangai 61 yd. run (C.Santos kick) (1-61, 0:10)")
    check("run wording", ("K.Monangai", "61"), (m.group(1), m.group(2)))

    m = FG.match("E.Pineiro 56 yd. Field Goal (4-5, 1:25)")
    check("field goal wording", ("E.Pineiro", "56"), (m.group(1), m.group(2)))

    m = RET_TD.match("T.Hufanga 66 yd. interception return (W.Lutz kick)")
    check("interception return", ("T.Hufanga", "66", "interception"),
          (m.group(1), m.group(2), m.group(3)))

    m = EZ_REC.match("G.Halton fumble recovery in end zone (E.Pineiro kick)")
    check("end-zone recovery has no yardage", "G.Halton", m.group(1))

    # Week 3, Green Bay: a two-point pass names passer then receiver.
    m = TWO_PT.search("Bi.Robinson 2 yd. run (M.Penix-C.Blair pass) (8-67, 4:45)")
    check("two-point passer", "M.Penix", m.group(1))
    check("two-point receiver", "C.Blair", m.group(2))
    check("two-point kind", "pass", m.group(3))

    check("extra point kicker", "J.Bates",
          XP_KICK.search("A.St. Brown 19 yd. pass from J.Goff (J.Bates kick)").group(1))
    check("failed conversion is not an extra point", None,
          XP_KICK.search("J.Palmer 34 yd. pass from J.Allen (pass failed)"))

    # Every form above must be recognised by the verifier, or the play
    # would be reported as unknown rather than scored.
    for desc in ("D.Samuel 82 yd. pass play by B.Purdy (E.Pineiro kick)",
                 "G.Halton fumble recovery in end zone (E.Pineiro kick)",
                 "Penalty on J.Alt enforced in end zone for a Safety",
                 "M.Price 86 yd. punt return (W.Reichard kick)"):
        check(f"verifier knows {desc[:28]!r}", True,
              any(r.search(desc) for r in KNOWN_FORMS))


def test_long_td_comes_from_scoring_summary():
    # Week 1, Travis Kelce: a 59-yard reception and no touchdown. The LG
    # column must never produce a bonus.
    g = {
        "file": "t.txt",
        "home_rushing": [], "home_passing": [],
        "home_receiving": [("T.Kelce", ["5", "3", "71", "23.7", "59", "0"])],
        "home_punt_ret": [], "home_ko_ret": [],
        "scoring_plays": [],
    }
    row = blank_row()
    offense_row(row, g, "home", "TE", "Travis", "Kelce")
    check("long reception recorded", ("3", "71"), (row["rec"], row["rec_yds"]))
    check("no bonus without a long touchdown", "", row["td_50plus"])

    # Week 5, Jaylen Warren: an 80-yard receiving score and a run of
    # exactly 50, which qualifies. Both bonuses are his.
    g["home_receiving"] = [("J.Warren", ["9", "6", "87", "14.5", "80", "1"])]
    g["home_rushing"] = [("J.Warren", ["18", "101", "5.6", "50", "1"])]
    g["scoring_plays"] = [
        {"team": "Steelers", "desc": "J.Warren 80 yd. pass from A.Rodgers (C.Boswell kick)"},
        {"team": "Steelers", "desc": "J.Warren 50 yd. run (C.Boswell kick)"},
    ]
    row = blank_row()
    offense_row(row, g, "home", "RB", "Jaylen", "Warren")
    check("two long touchdowns in one game", 2, row["td_50plus"])

    # The quarterback on that 80-yard throw earns the bonus too.
    g["home_receiving"], g["home_rushing"] = [], []
    g["home_passing"] = [("A.Rodgers", ["30", "20", "235", "0/0", "3", "80", "0", "120.0"])]
    row = blank_row()
    offense_row(row, g, "home", "QB", "Aaron", "Rodgers")
    check("passer earns the long bonus", 1, row["td_50plus"])
    check("gross passing yards used", "235", row["pass_yds"])


def test_end_zone_fumble_is_defensive_only_when_opp_rec():
    # Week 5, San Francisco: Halton forced Holani's fumble and recovered
    # it in Seattle's end zone -- an OPP-REC touchdown, so a defensive
    # score worth six to the 49ers.
    base = {
        "file": "t.txt", "vis_score": 32, "home_score": 29,
        "vis_interceptions": [], "vis_safeties": 0,
        "scoring_plays": [{"team": "49ers",
                           "desc": "G.Halton fumble recovery in end zone (E.Pineiro kick)"}],
        "defense": {"San Francisco 49ers": {"rows": [], "total": ["0"] * 20}},
    }
    opp = dict(base)
    opp["fumbles"] = {"San Francisco 49ers": {
        # FUM LOST OWN-REC YDS TD FORCED OPP-REC YDS TD OUT-BDS
        "rows": [("G.Halton", ["0", "0", "0", "0", "0", "1", "1", "0", "1", "0"])],
        "total": ["0", "0", "0", "0", "0", "1", "1", "0", "1", "0"]}}
    row, problems = blank_row(), []
    defense_row(row, opp, "vis", "San Francisco 49ers", problems)
    check("opponent recovery in end zone is a defensive TD", 1, row["def_td"])
    check("no complaint raised", [], problems)

    # The same wording for a player falling on his OWN team's fumble is
    # an offensive score and must credit the defense with nothing.
    own = dict(base)
    own["fumbles"] = {"San Francisco 49ers": {
        "rows": [("G.Halton", ["0", "0", "1", "0", "1", "0", "0", "0", "0", "0"])],
        "total": ["0", "0", "1", "0", "1", "0", "0", "0", "0", "0"]}}
    row, problems = blank_row(), []
    defense_row(row, own, "vis", "San Francisco 49ers", problems)
    check("own recovery in end zone is not a defensive TD", 0, row["def_td"])

    # Unclassifiable recoveries are reported, never guessed.
    unknown = dict(base)
    unknown["fumbles"] = {"San Francisco 49ers": {"rows": [], "total": ["0"] * 10}}
    row, problems = blank_row(), []
    defense_row(row, unknown, "vis", "San Francisco 49ers", problems)
    check("unclassifiable recovery is reported", 1, len(problems))


def test_defense_aggregates():
    # Week 1, Cincinnati: four opponent fumbles recovered, one returned
    # 27 yards for a score. Fumble return yards count only because the
    # return ended in a touchdown.
    g = {
        "file": "t.txt", "home_score": 33, "vis_score": 27,
        "home_interceptions": [], "home_safeties": 0,
        "defense": {"Cincinnati Bengals": {"rows": [],
                                           "total": ["0", "0", "0", "4"] + ["0"] * 16}},
        "fumbles": {"Cincinnati Bengals": {
            "rows": [], "total": ["0", "0", "0", "0", "0", "4", "4", "27", "1", "0"]}},
        "scoring_plays": [{"team": "Bengals",
                           "desc": "D.Knight 27 yd. fumble return (E.McPherson kick)"}],
    }
    row, problems = blank_row(), []
    defense_row(row, g, "home", "Cincinnati Bengals", problems)
    check("sacks from Total row", "4", row["def_sack"])
    check("opponent fumbles recovered", 4, row["def_fum_rec"])
    check("defensive touchdown", 1, row["def_td"])
    check("fumble return yards scored", 27, row["def_fum_ret_td_yds"])
    check("points allowed is the opponent's score", 27, row["pts_allowed"])
    check("short return earns no long bonus", 0, row["def_td_50plus"])

    # A special-teams return touchdown pays the returner, never the
    # defense (week 5, Minnesota's 86-yard punt return).
    g["scoring_plays"] = [{"team": "Bengals",
                           "desc": "M.Price 86 yd. punt return (W.Reichard kick)"}]
    row, problems = blank_row(), []
    defense_row(row, g, "home", "Cincinnati Bengals", problems)
    check("punt return TD does not credit the defense", 0, row["def_td"])


def test_status_overrides():
    ov = [
        {"name": "Josh Jacobs", "first": 1, "last": None, "status": "OUT", "note": ""},
        {"name": "A.J. Brown", "first": 2, "last": 6, "status": "IR", "note": ""},
    ]
    check("open-ended override applies later", "OUT",
          override_for(ov, "Josh Jacobs", 9)["status"])
    check("override not applied before its first week", None,
          override_for(ov, "A.J. Brown", 1))
    check("override applies inside its window", "IR",
          override_for(ov, "A.J. Brown", 4)["status"])
    check("override expires after its last week", None,
          override_for(ov, "A.J. Brown", 7))
    check("unknown player has no override", None,
          override_for(ov, "Someone Else", 3))


def test_bye_versus_not_yet_pulled():
    """A team with no Game Book is on a bye or has not been pulled yet,
    and the schedule is the only thing that tells them apart. Getting it
    wrong either drops a real bye out of the file or silently excludes a
    game that was simply pulled early."""
    import os
    import tempfile

    sched = ("week,visitor,home\n"
             "5,Chicago Bears,Green Bay Packers\n"
             "5,Detroit Lions,Arizona Cardinals\n")
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(sched)
    try:
        playing = load_schedule(path, 5)
        check("teams playing this week", 4, len(playing))
        check("scheduled team found", True, "Green Bay Packers" in playing)
        check("team absent from the week is on a bye", False,
              "Carolina Panthers" in playing)
        check("other weeks ignored", None, load_schedule(path, 6))
        check("missing file yields no schedule", None,
              load_schedule(path + ".nope", 5))
    finally:
        os.unlink(path)

    # Now the decision itself. Carolina is not in the schedule for this
    # week, so a Panther gets a BYE row; Detroit is scheduled but its
    # Game Book is absent, so a Lion gets no row at all.
    players = [
        {"name": "Chuba Hubbard", "last_name": "Hubbard", "first_name": "Chuba",
         "position": "RB", "team": "Carolina Panthers"},
        {"name": "Jahmyr Gibbs", "last_name": "Gibbs", "first_name": "Jahmyr",
         "position": "RB", "team": "Detroit Lions"},
    ]
    scheduled = {"Chicago Bears", "Green Bay Packers",
                 "Detroit Lions", "Arizona Cardinals"}
    rows, problems = build(5, [], players, [], scheduled)
    check("one row written, not two", 1, len(rows))
    check("the bye is recorded", ("Chuba Hubbard", "BYE"),
          (rows[0]["name"], rows[0]["status"]))
    check("the unpulled game leaves no row", [],
          [r for r in rows if r["team"] == "Detroit Lions"])
    check("no complaint for either", [], problems)

    # With no schedule at all, neither is assumed and both are reported.
    rows, problems = build(5, [], players, [], None)
    check("without a schedule nothing is guessed", 0, len(rows))
    check("and both are reported", 2, len(problems))


def test_absent_player_gets_blank_status_not_active():
    """The trap that scored Josh Jacobs a real 0.00 in week 1."""
    g = {
        "file": "t.txt",
        "vis_rushing": [], "vis_passing": [], "vis_receiving": [],
        "vis_punt_ret": [], "vis_ko_ret": [],
        "vis_lineup": "RB 30 C.Brooks", "vis_subs": "RB 32 M.Lloyd",
        "vis_inactive": "LB 59 T.Hopper", "vis_dnp": "QB 6 T.Taylor",
        "visitor": "Green Bay Packers", "home": "Minnesota Vikings",
        "scoring_plays": [],
    }
    players = [{"name": "Josh Jacobs", "last_name": "Jacobs",
                "first_name": "Josh", "position": "RB",
                "team": "Green Bay Packers"}]
    rows, problems = build(2, [g], players, [], {"Green Bay Packers"})
    check("absent player is not active", "", rows[0]["status"])
    check("and is reported", 1, len(problems))

    # With the reason recorded, the status is filled and the complaint
    # goes away -- and it survives a re-run, which a hand edit does not.
    ov = [{"name": "Josh Jacobs", "first": 1, "last": None,
           "status": "OUT", "note": "exempt list"}]
    rows, problems = build(2, [g], players, ov, {"Green Bay Packers"})
    check("override supplies the status", "OUT", rows[0]["status"])
    check("and silences the complaint", [], problems)

    # A player the Game Book itself lists as inactive is explained by the
    # document, which wins over any override.
    g["vis_inactive"] = "LB 59 T.Hopper, RB 8 J.Jacobs"
    rows, _ = build(2, [g], players, ov, {"Green Bay Packers"})
    check("the Game Book beats the override", "INACTIVE", rows[0]["status"])


def main():
    for fn in (test_abbreviations, test_team_sacks_total, test_two_column_split,
               test_negative_and_zero_lines, test_scoring_play_forms,
               test_long_td_comes_from_scoring_summary,
               test_end_zone_fumble_is_defensive_only_when_opp_rec,
               test_defense_aggregates, test_status_overrides,
               test_bye_versus_not_yet_pulled,
               test_absent_player_gets_blank_status_not_active):
        fn()
    for f in FAILS:
        print("FAIL ", f)
    print(f"\n{CHECKS - len(FAILS)}/{CHECKS} checks passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
