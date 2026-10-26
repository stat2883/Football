#!/usr/bin/env python3
"""Turn a week's downloaded Game Books into the raw weekly CSV.

    python3 fetch_week.py 5          # download the Game Books first
    python3 parse_week.py 5          # -> weeks/raw-week05.csv
    python3 run_week.py 5 weeks/raw-week05.csv
    python3 build_cumulative.py

This is the step that used to be done by hand, and the traps it walks
around are the ones that were found the hard way. They are documented in
SESSION_INSTRUCTIONS.md section 4; every one of them is implemented here
and asserted by test_parse_week.py:

  * team sacks come from the defensive table's Total row, because an
    unattributed sack sits on a Team Sacks line no player row carries
  * td_50plus comes from the Scoring Plays section only, never from a
    long-yardage column
  * gross passing yards from the PASSING table, never NET YARDS PASSING
  * a lateral score reads "pass play by" instead of "pass from" and still
    credits the quarterback with the touchdown
  * a fumble recovered in the opponent's end zone scores with no yardage,
    and is a defensive touchdown only when the Fumbles table records it
    as an OPP-REC score rather than an OWN-REC one
  * abbreviations are matched as a prefix of the first name, since the
    Game Book lengthens initials (Bri./Bry.) to separate players
  * a player absent from the Game Book entirely is not "inactive" and is
    never left as active; his status must be confirmed outside the
    document and recorded in weeks/status-overrides.csv

Nothing here is scored. The output is raw stats, which is what makes a
later scoring-rule change re-runnable without re-pulling anything.

Exit status is non-zero if anything needs a human: an unresolved status,
an unknown scoring-play format, or a failed cross-check. Rows whose
status could not be established are written with a BLANK status, which
run_week.py then refuses by design rather than scoring as a real zero.
"""

import argparse
import csv
import os
import re
import sys

from positions import SUFFIXES

HERE = os.path.dirname(os.path.abspath(__file__))

COLUMNS = ["name", "position", "team", "status", "pass_yds", "pass_td", "pass_2pt",
           "int_thrown", "rush_yds", "rush_td", "rush_2pt", "rec", "rec_yds",
           "rec_td", "rec_2pt", "td_50plus", "st_ret_td", "fg_0_39", "fg_40_49",
           "fg_50_59", "fg_60plus", "xp_made", "def_int", "def_sack",
           "def_fum_rec", "def_safety", "def_td", "def_int_ret_yds",
           "def_fum_ret_td_yds", "def_td_50plus", "pts_allowed"]

NUM = re.compile(r"^-?\d+(\.\d+)?$")

# Scoring-summary forms. Any description matching none of these is reported
# rather than silently dropped -- that is how the end-zone fumble recovery
# was found in week 5 after four weeks of going unnoticed.
RUN_TD = re.compile(r"^(\S[\w.' -]*?)\s+(\d+)\s+yd\.\s+run\b")
PASS_TD = re.compile(r"^(\S[\w.' -]*?)\s+(\d+)\s+yd\.\s+pass (?:from|play by)\s+(\S[\w.' -]*?)\s*(?:\(|$)")
FG = re.compile(r"^(\S[\w.' -]*?)\s+(\d+)\s+yd\.\s+Field Goal")
RET_TD = re.compile(r"^(\S[\w.' -]*?)\s+(\d+)\s+yd\.\s+(interception|fumble|punt|kickoff)\s+return")
EZ_REC = re.compile(r"^(\S[\w.' -]*?)\s+fumble recovery in end zone")
XP_KICK = re.compile(r"\((\S[\w.' -]*?)\s+kick\)")
TWO_PT = re.compile(r"\((\S[\w.' -]*?)-(\S[\w.' -]*?)\s+(pass|run)\)")
SAFETY = re.compile(r"[Ss]afety")

KNOWN_FORMS = (RUN_TD, PASS_TD, FG, RET_TD, EZ_REC, SAFETY)


# --------------------------------------------------------------------------
# Game Book text parsing
# --------------------------------------------------------------------------

def is_stat(tok):
    return bool(NUM.match(tok)) or "/" in tok or tok.endswith("%")


def split_name_stats(line, n_expected):
    """'A.St. Brown  14 10 67 ...' -> ('A.St. Brown', [...]).

    The name may contain spaces and periods, so the split point is the
    first index from which every remaining token is stat-shaped and the
    count is exactly right. Returns (None, None) when the line is not a
    data row of this table.
    """
    toks = line.split()
    for i in range(1, len(toks) + 1):
        rest = toks[i:]
        if len(rest) == n_expected and all(is_stat(t) for t in rest):
            return " ".join(toks[:i]), rest
    return None, None


def two_col_section(lines, idx, keyword, n_stats):
    """Parse a visitor-left / home-right table sharing one header line."""
    header = lines[idx]
    cut = header.find(keyword, header.find(keyword) + 1)
    if cut == -1:
        return [], []
    vis, home = [], []
    for ln in lines[idx + 1:]:
        if not ln.strip():
            break
        for side, chunk in ((vis, ln[:cut]), (home, ln[cut:])):
            s = chunk.strip()
            if not s or s.startswith("Total"):
                continue
            name, stats = split_name_stats(s, n_stats)
            if name:
                side.append((name, stats))
        if ln[:cut].strip().startswith("Total") and ln[cut:].strip().startswith("Total"):
            break
    return vis, home


def one_col_table(lines, idx, n_stats, lookahead=60):
    """Parse a single-column table, returning (rows, total_row).

    The Total row is returned separately and is the authoritative figure
    for team aggregates: the defensive table carries unattributed Team
    Sacks that no player row reflects. The search for Total runs past
    blank lines and page breaks, because a table can be split across
    pages with its header repeated.
    """
    rows, total = [], None
    for ln in lines[idx + 1:idx + 1 + lookahead]:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("Total"):
            _, total = split_name_stats(s, n_stats)
            break
        name, stats = split_name_stats(s, n_stats)
        if name:
            rows.append((name, stats))
    return rows, total


def block_after(lines, label, max_lines=14):
    """Collect the wrapped two-column text under a doubled header label."""
    for i, ln in enumerate(lines):
        if ln.count(label) >= 2:
            blk = []
            for s in lines[i + 1:i + 1 + max_lines]:
                if not s.strip():
                    if blk:
                        break
                    continue
                if any(k in s for k in ("Substitutions", "Did Not Play",
                                        "Not Active", "Field Goals")):
                    break
                blk.append(s.rstrip())
            return blk
    return []


def split_block(blk):
    """Split a wrapped two-column block at its whitespace gutter."""
    if not blk:
        return "", ""
    width = max(len(l) for l in blk)
    lo, hi = int(width * 0.25), int(width * 0.92)
    runs, start = [], None
    for c in range(lo, hi):
        if all(c >= len(l) or l[c] == " " for l in blk):
            if start is None:
                start = c
        else:
            if start is not None and c - start >= 3:
                runs.append((start, c))
            start = None
    if start is not None and hi - start >= 3:
        runs.append((start, hi))
    runs = [r for r in runs if r[0] < width * 0.70]
    if not runs:
        return "\n".join(blk), ""
    cut = max(runs, key=lambda r: r[1] - r[0])[1]
    left = " ".join(l[:cut].strip() for l in blk if l[:cut].strip())
    right = " ".join(l[cut:].strip() for l in blk if l[cut:].strip())
    return left, right


def parse_gamebook(path):
    """One Game Book's extracted text -> a dict of everything needed."""
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    g = {"file": os.path.basename(path)}

    for ln in lines[:12]:
        m = re.search(r"Date:\s+\w+,\s+(\d+/\d+/\d+)\s+(.+?)\s+at\s+(.+?)\s+Start Time:", ln)
        if m:
            g["date"], g["visitor"], g["home"] = m.group(1), m.group(2).strip(), m.group(3).strip()
            break
    if "visitor" not in g:
        raise ValueError(f"{g['file']}: could not read the teams from the header")

    for ln in lines:
        if ln.strip().startswith("FINAL SCORE"):
            n = re.findall(r"-?\d+", ln)
            g["vis_score"], g["home_score"] = int(n[-2]), int(n[-1])
            break

    g["vis_safeties"] = g["home_safeties"] = 0
    for ln in lines:
        if ln.strip().startswith("SAFETIES"):
            n = re.findall(r"-?\d+", ln)
            if len(n) >= 2:
                g["vis_safeties"], g["home_safeties"] = int(n[-2]), int(n[-1])
            break

    # Per-player stat tables. The first occurrence is the full game; the
    # ones further down are the half summaries.
    seen = set()
    for i, ln in enumerate(lines):
        st = ln.strip()
        for kw, key, n in (("RUSHING", "rushing", 5), ("PASSING", "passing", 8),
                           ("PASS RECEIVING", "receiving", 6),
                           ("INTERCEPTIONS", "interceptions", 5),
                           ("PUNT RETURNS", "punt_ret", 6),
                           ("KICKOFF RETURNS", "ko_ret", 6)):
            if key in seen or not st.startswith(kw) or ln.count(kw) < 2:
                continue
            if kw == "PASSING" and st.startswith("PASS RECEIVING"):
                continue
            g["vis_" + key], g["home_" + key] = two_col_section(lines, i, kw, n)
            seen.add(key)
    for key in ("rushing", "passing", "receiving", "interceptions", "punt_ret", "ko_ret"):
        g.setdefault("vis_" + key, [])
        g.setdefault("home_" + key, [])

    # FUMBLES and Final Defensive Statistics: one single-column table per
    # team, each labelled by the team name on its own line just above.
    g["fumbles"], g["defense"] = {}, {}
    for i, ln in enumerate(lines):
        if ln.strip().startswith("FUMBLES") and "FUM" in ln and "LOST" in ln:
            team = lines[i - 1].strip()
            if team in (g["visitor"], g["home"]) and team not in g["fumbles"]:
                rows, total = one_col_table(lines, i, 10)
                g["fumbles"][team] = {"rows": rows, "total": total}
        if "Regular Defensive Plays" in ln:
            team = ln.split("Regular Defensive Plays")[0].strip()
            if team in (g["visitor"], g["home"]) and team not in g["defense"]:
                hdr = next((j for j in range(i + 1, min(i + 6, len(lines)))
                            if "TKL" in lines[j] and "COMB" in lines[j]), None)
                if hdr is not None:
                    rows, total = one_col_table(lines, hdr, 20)
                    g["defense"][team] = {"rows": rows, "total": total}

    # Roster blocks, for telling "dressed but did not play" from "not on
    # the gameday roster at all".
    for label, key in (("Substitutions", "subs"), ("Did Not Play", "dnp"),
                       ("Not Active", "inactive")):
        g["vis_" + key], g["home_" + key] = split_block(block_after(lines, label))
    g["vis_lineup"], g["home_lineup"] = split_block(block_after(lines, "Offense"))

    # Scoring plays. Half summaries repeat them, so dedupe on the play.
    plays, seen_p, in_sp = [], set(), False
    for ln in lines:
        if ln.strip().startswith("Scoring Plays"):
            in_sp = True
            continue
        if not in_sp:
            continue
        if ln.strip().startswith("Team") and "Qtr" in ln:
            continue
        m = re.match(r"\s*(\S[\w .'-]*?)\s+(\d)\s+(\d+:\d\d)\s+(.+?)\s{2,}(\d+)\s+(\d+)\s*$", ln)
        if m:
            desc = re.sub(r"\s+", " ", m.group(4)).strip()
            k = (int(m.group(2)), m.group(3), desc)
            if k not in seen_p:
                seen_p.add(k)
                plays.append({"team": m.group(1).strip(), "qtr": int(m.group(2)),
                              "desc": desc, "vis": int(m.group(5)), "home": int(m.group(6))})
        elif ln.strip().startswith("Paid Attendance") or "First Half Summary" in ln:
            in_sp = False
    g["scoring_plays"] = plays
    return g


# --------------------------------------------------------------------------
# name matching
# --------------------------------------------------------------------------

def bare_surname(last):
    parts = last.split()
    while len(parts) > 1 and parts[-1].lower().rstrip(".") in SUFFIXES:
        parts.pop()
    return " ".join(parts)


def abbrev_match(gb_name, first, surname):
    """Does a Game Book abbreviation refer to this player?

    The abbreviation is an initial plus the surname, but the Game Book
    LENGTHENS the initial to separate teammates: Jacksonville fielded
    both Bri.Thomas (Brian) and Bry.Thomas (Bryce). Matching the prefix
    against the whole first name keeps those apart; matching only the
    first letter would hand Bryce's line to Brian.
    """
    m = re.match(r"^([A-Z][a-z]{0,2})\.(.+)$", gb_name.strip())
    if not m:
        return False
    return (first.lower().startswith(m.group(1).lower())
            and m.group(2).strip().lower() == surname.lower())


def find(table, first, surname):
    return [(n, s) for n, s in table if abbrev_match(n, first, surname)]


def in_block(block, first, surname):
    """Is this player named in a comma-separated roster block?"""
    for entry in block.split(","):
        toks = entry.strip().split()
        if toks and abbrev_match(toks[-1], first, surname):
            return True
    return False


def scored_by(team, play_team):
    """Did `team` (full name) score this play (labelled by nickname)?"""
    return team.endswith(play_team) or play_team in team


# --------------------------------------------------------------------------
# status overrides
# --------------------------------------------------------------------------

def load_overrides(path):
    """weeks/status-overrides.csv: name,first_week,last_week,status,note.

    A player on IR or the Commissioner's Exempt List is absent from the
    Game Book entirely, so the document cannot say why. Recording it here
    rather than editing the raw file by hand means the answer survives a
    re-run -- a hand edit does not, and silently reverts to a scored 0.00.
    An empty last_week means "still out".
    """
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not (r.get("name") or "").strip():
                continue
            out.append({
                "name": r["name"].strip(),
                "first": int(r["first_week"]),
                "last": int(r["last_week"]) if (r.get("last_week") or "").strip() else None,
                "status": r["status"].strip(),
                "note": (r.get("note") or "").strip(),
            })
    return out


def override_for(overrides, name, week):
    for o in overrides:
        if o["name"] == name and week >= o["first"] and (o["last"] is None or week <= o["last"]):
            return o
    return None


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

def verify(g, raw_text):
    """Cross-check the parse against the Game Book's own team totals.

    Each figure the scoring needs is available twice in the document, so
    a parse error shows up as a disagreement rather than as a plausible
    wrong number. Returns a list of complaints.
    """
    bad = []
    f = g["file"]

    plays = g["scoring_plays"]
    if plays:
        last = plays[-1]
        if (last["vis"], last["home"]) != (g["vis_score"], g["home_score"]):
            bad.append(f"{f}: scoring plays end {last['vis']}-{last['home']} "
                       f"but FINAL SCORE is {g['vis_score']}-{g['home_score']}")
    for p in plays:
        if not any(r.search(p["desc"]) for r in KNOWN_FORMS):
            bad.append(f"{f}: unrecognised scoring play -- {p['desc']!r}")

    for team in (g["visitor"], g["home"]):
        if team not in g["defense"] or g["defense"][team]["total"] is None:
            bad.append(f"{f}: no defensive Total row for {team}")
        if team not in g["fumbles"] or g["fumbles"][team]["total"] is None:
            bad.append(f"{f}: no fumbles Total row for {team}")
    if bad:
        return bad

    m = re.search(r"Times thrown - yards lost attempting to pass\s+"
                  r"(\d+)-(-?\d+)\s+(\d+)-(-?\d+)", raw_text)
    thrown = {"vis": int(m.group(1)), "home": int(m.group(3))} if m else None
    fl = re.search(r"^FUMBLES Number and Lost\s+(\d+)-(\d+)\s+(\d+)-(\d+)", raw_text, re.M)
    lost = {"vis": int(fl.group(2)), "home": int(fl.group(4))} if fl else None

    for side, team in (("vis", g["visitor"]), ("home", g["home"])):
        other = "home" if side == "vis" else "vis"
        tot = g["defense"][team]["total"]
        sacks, dints = float(tot[3]), int(tot[7])
        thrown_by_opp = sum(int(s[6]) for _, s in g[other + "_passing"])
        int_rows = sum(int(s[0]) for _, s in g[side + "_interceptions"])
        if thrown is not None and sacks != thrown[other]:
            bad.append(f"{f}: {team} sacks -- defensive Total says {sacks:g}, "
                       f"team summary says {thrown[other]}")
        if not (dints == int_rows == thrown_by_opp):
            bad.append(f"{f}: {team} interceptions -- defensive table {dints}, "
                       f"interceptions table {int_rows}, opponent threw {thrown_by_opp}")
        if lost is not None:
            rec = int(g["fumbles"][team]["total"][6])
            if rec != lost[other]:
                bad.append(f"{f}: {team} recovered {rec} opponent fumbles but the "
                           f"opponent is shown losing {lost[other]}")
    return bad


# --------------------------------------------------------------------------
# building the raw rows
# --------------------------------------------------------------------------

def defense_row(row, g, side, team, problems):
    other = "home" if side == "vis" else "vis"
    tot = g["defense"][team]["total"]

    # The Total row, not a sum of player rows: unattributed Team Sacks.
    sacks = float(tot[3])
    ints = g[side + "_interceptions"]
    n_int = sum(int(s[0]) for _, s in ints)
    int_yds = sum(int(s[1]) for _, s in ints)
    opp_rec = int(g["fumbles"][team]["total"][6])

    dtd = dtd50 = fum_td_yds = 0
    for p in g["scoring_plays"]:
        if not scored_by(team, p["team"]):
            continue
        m = RET_TD.match(p["desc"])
        if m and m.group(3) in ("interception", "fumble"):
            yds = int(m.group(2))
            dtd += 1
            if yds >= 50:
                dtd50 += 1
            if m.group(3) == "fumble":
                # Fumble return yards score only when the return scored,
                # which is exactly the case being counted here.
                fum_td_yds += yds
            continue
        m = EZ_REC.match(p["desc"])
        if m:
            # No yardage, so no "N yd. fumble return" wording. Defensive
            # only if the Fumbles table calls it an OPP-REC touchdown; a
            # player falling on his own team's fumble in the end zone is
            # an offensive score and credits this defense with nothing.
            who = m.group(1).strip()
            hit = [s for n_, s in g["fumbles"][team]["rows"] if n_.strip() == who]
            if hit and int(hit[0][8]) >= 1:
                dtd += 1
            elif hit and int(hit[0][4]) >= 1:
                pass
            else:
                problems.append(f"{team}: cannot classify end-zone fumble "
                                f"touchdown by {who} in {g['file']}")

    row.update(status="active", def_int=n_int, def_sack=f"{sacks:g}",
               def_fum_rec=opp_rec, def_safety=g[side + "_safeties"],
               def_td=dtd, def_int_ret_yds=int_yds,
               def_fum_ret_td_yds=fum_td_yds, def_td_50plus=dtd50,
               pts_allowed=g[other + "_score"])


def offense_row(row, g, side, pos, first, surname):
    rush = find(g[side + "_rushing"], first, surname)
    pas = find(g[side + "_passing"], first, surname)
    rec = find(g[side + "_receiving"], first, surname)

    if rush:
        # Negative rushing yards are real and subtract. A quarterback
        # absent from this table has no rush yards even though he was
        # sacked -- sack yardage is not rushing and is never recorded.
        row["rush_yds"], row["rush_td"] = rush[0][1][1], rush[0][1][4]
    if pas:
        # Gross yards from this table, never NET YARDS PASSING, which is
        # a team figure with sack yardage already subtracted.
        row["pass_yds"], row["pass_td"], row["int_thrown"] = (
            pas[0][1][2], pas[0][1][4], pas[0][1][6])
    if rec:
        row["rec"], row["rec_yds"], row["rec_td"] = (
            rec[0][1][1], rec[0][1][2], rec[0][1][5])

    td50 = st_td = xp = 0
    fg = {"fg_0_39": 0, "fg_40_49": 0, "fg_50_59": 0, "fg_60plus": 0}
    for p in g["scoring_plays"]:
        d = p["desc"]

        # td_50plus comes from here and nowhere else. A long reception in
        # the LG column says nothing about whether the touchdown was long.
        m = RUN_TD.match(d)
        if m and int(m.group(2)) >= 50 and abbrev_match(m.group(1), first, surname):
            td50 += 1
        m = PASS_TD.match(d)
        if m and int(m.group(2)) >= 50:
            # Pays every player credited on the play: the scorer and the
            # quarterback both, including when a lateral made the wording
            # "pass play by" and the quarterback's own throw was short.
            if abbrev_match(m.group(1), first, surname) or abbrev_match(m.group(3), first, surname):
                td50 += 1
        m = RET_TD.match(d)
        if m and m.group(3) in ("punt", "kickoff") and abbrev_match(m.group(1), first, surname):
            st_td += 1
            if int(m.group(2)) >= 50:
                td50 += 1
        m = FG.match(d)
        if m and abbrev_match(m.group(1), first, surname):
            y = int(m.group(2))
            fg["fg_0_39" if y < 40 else "fg_40_49" if y < 50
               else "fg_50_59" if y < 60 else "fg_60plus"] += 1
        m = XP_KICK.search(d)
        if m and abbrev_match(m.group(1), first, surname):
            xp += 1
        m = TWO_PT.search(d)
        if m:
            if abbrev_match(m.group(1), first, surname):
                row["pass_2pt" if m.group(3) == "pass" else "rush_2pt"] = 1
            elif abbrev_match(m.group(2), first, surname):
                row["rec_2pt" if m.group(3) == "pass" else "rush_2pt"] = 1

    if td50:
        row["td_50plus"] = td50
    if st_td:
        row["st_ret_td"] = st_td
    if pos == "K":
        row.update(fg)
        row["xp_made"] = xp
    return bool(rush or pas or rec
                or find(g[side + "_punt_ret"], first, surname)
                or find(g[side + "_ko_ret"], first, surname))


def build(week, games, players, overrides, scheduled):
    """Returns (rows, problems). A player whose game is not among the
    downloaded Game Books gets NO ROW, which is how a partial week is
    told apart from a bye: no row means not pulled yet."""
    team_game = {}
    for g in games:
        team_game[g["visitor"]] = (g, "vis")
        team_game[g["home"]] = (g, "home")

    rows, problems = [], []
    for p in players:
        name, pos, team = p["name"], p["position"], p["team"]
        row = dict.fromkeys(COLUMNS, "")
        row.update(name=name, position=pos, team=team)

        if team not in team_game:
            nick = team.split()[-1].lower()
            if scheduled is not None and nick not in scheduled:
                row["status"] = "BYE"
                rows.append(row)
            elif scheduled is None:
                problems.append(f"{name}: no Game Book for {team}, and the "
                                "schedule was unavailable, so bye and "
                                "not-yet-pulled cannot be told apart")
            # otherwise: scheduled but not downloaded -> no row at all
            continue

        g, side = team_game[team]
        first = p["first_name"] or p["last_name"]
        surname = bare_surname(p["last_name"])

        if pos == "DEF":
            defense_row(row, g, side, team, problems)
            rows.append(row)
            continue

        ov = override_for(overrides, name, week)
        inactive = in_block(g[side + "_inactive"], first, surname)
        dnp = in_block(g[side + "_dnp"], first, surname)
        listed = (in_block(g[side + "_lineup"], first, surname)
                  or in_block(g[side + "_subs"], first, surname))

        played = offense_row(row, g, side, pos, first, surname)

        if inactive or dnp:
            # Dressed, so the Game Book itself says why. It wins over an
            # override, which exists for players the document omits.
            for col in COLUMNS[4:]:
                row[col] = ""
            row["status"] = "INACTIVE" if inactive else "DNP"
        elif played or listed:
            row["status"] = "active"
        elif ov:
            row["status"] = ov["status"]
        else:
            # Absent from the document entirely and unexplained. Left
            # BLANK on purpose: run_week.py refuses a blank status, which
            # is far safer than scoring a real 0.00 for a game the player
            # was never eligible for.
            row["status"] = ""
            problems.append(
                f"{name} ({pos}, {team}): absent from {g['file']} entirely -- "
                "not in the lineup, substitutions, Did Not Play or Not Active. "
                "Confirm why outside the Game Book and add a row to "
                "weeks/status-overrides.csv")
        rows.append(row)
    return rows, problems


def schedule_nicknames(season, week):
    """Team nicknames with a game this week, used to tell a bye from a
    game that simply has not been pulled yet. Returns None if the
    schedule cannot be reached, in which case neither is assumed."""
    try:
        from fetch_week import game_slugs
        slugs = game_slugs(season, week)
    except Exception as exc:
        print(f"  schedule unavailable ({exc}); byes cannot be detected",
              file=sys.stderr)
        return None
    nicks = set()
    for s in slugs:
        base = s.rsplit("/", 1)[-1].split(f"-{season}-reg-{week}")[0]
        if "-at-" in base:
            nicks.update(base.split("-at-"))
    return nicks or None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("week", type=int)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--gamebooks", help="default gamebooks/weekNN")
    ap.add_argument("--out", help="default weeks/raw-weekNN.csv")
    ap.add_argument("--players", default=os.path.join(HERE, "players.csv"))
    ap.add_argument("--overrides",
                    default=os.path.join(HERE, "weeks", "status-overrides.csv"))
    ap.add_argument("--no-schedule", action="store_true",
                    help="skip the schedule lookup; byes are not detected")
    args = ap.parse_args()

    wk = f"{args.week:02d}"
    gbdir = args.gamebooks or os.path.join(HERE, "gamebooks", f"week{wk}")
    out = args.out or os.path.join(HERE, "weeks", f"raw-week{wk}.csv")

    if not os.path.isdir(gbdir):
        sys.exit(f"No Game Books at {gbdir}. Run: python3 fetch_week.py {args.week}")
    texts = sorted(f for f in os.listdir(gbdir) if f.endswith(".txt"))
    if not texts:
        sys.exit(f"{gbdir} has no extracted text. Run fetch_week.py again.")

    games, problems = [], []
    for fn in texts:
        path = os.path.join(gbdir, fn)
        g = parse_gamebook(path)
        games.append(g)
        problems += verify(g, open(path, encoding="utf-8", errors="replace").read())

    with open(args.players, newline="", encoding="utf-8") as fh:
        players = list(csv.DictReader(fh))
    overrides = load_overrides(args.overrides)
    scheduled = None if args.no_schedule else schedule_nicknames(args.season, args.week)

    rows, build_problems = build(args.week, games, players, overrides, scheduled)
    problems += build_problems

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[r["status"] or "(blank)"] = counts.get(r["status"] or "(blank)", 0) + 1
    print(f"{len(games)} Game Books -> {len(rows)} rows in "
          f"{os.path.relpath(out, HERE)}")
    print("  " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    missing = len(players) - len(rows)
    if missing:
        print(f"  {missing} player(s) have no row yet; their games are not "
              "in this download. Re-run fetch_week.py and this script.")

    if problems:
        print(f"\n{len(problems)} thing(s) need a human:")
        for pr in problems:
            print(f"  ! {pr}")
        print("\nRows with a blank status are deliberate; run_week.py will "
              "refuse them until they are resolved.")
        return 1
    print("\nAll cross-checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
