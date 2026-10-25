# Fantasy Football — Session Instructions

This file is the authoritative source for how sessions in this repository are
run. The Claude project instructions contain only what is needed to locate this
repository and find this file; everything else lives here.

If anything in this file conflicts with a stale instruction elsewhere, this file
wins. If the user gives a direct instruction during a session that differs from
this file, the user wins for that session — this file is the default, not a cage.

---

## 1. Session Start

1. Clone the repo with git via the bash tool:
   `git clone https://github.com/stat2883/Football.git`
   Cloning over https needs no token. A token is only required for pushing, and
   see §7 — none should be requested.
2. Read this file.
3. Read `players.csv` and `scoring.json`.

Do **not** use web search or `web_fetch` to reach the repo itself. Web search
**is** required for pulling weekly statistics (§4) — that restriction applies
only to reaching this repository.

If the repo cannot be reached, say so plainly rather than proceeding from memory.

---

## 2. Repository Structure

```
players.csv              players of interest (grows over time; see §3)
scoring.json             scoring rules — authoritative, read by score.py
score.py                 scoring engine
positions.py             per-position schemas and name handling
run_week.py              raw week -> six per-position weekly files
build_cumulative.py      weekly files -> six cumulative files
test_scoring.py          26 hand-checkable scoring cases
test_cumulative.py       14 checks on the summary columns
weeks/_TEMPLATE.csv      blank header row for a raw weekly pull
QB/ RB/ WR/ TE/ K/ DEF/  one directory per position
```

Each position directory holds that position's weekly files
(`Week06-QB.csv`) plus its cumulative file (`Cumulative-QB.csv`). By the end of
an 18-week season: 108 weekly files and 6 cumulative files.

---

## 3. players.csv

Columns: `name`, `last_name`, `first_name`, `position`, `team`.

`name` is natural order ("Amon-Ra St. Brown"). `last_name` and `first_name` are
stored explicitly rather than parsed, because suffixes (Jr, Sr, II, III) and
two-word surnames ("St. Brown") break naive splitting. Output files display
`"St. Brown, Amon-Ra"` — Last, First.

**This list only grows.** It is a watchlist of players of interest, not a single
roster. Players are never removed; a player added mid-season shows blanks for
earlier weeks, which correctly reads as "not tracked yet" rather than as missed
games.

DEF entries carry the team name in `name`, `last_name`, and `team`.

When adding a player, fill in `last_name` and `first_name` directly rather than
relying on a split.

---

## 4. Weekly Statistics Pull

**Canonical source: the official NFL Game Book PDF for each game.**

Tested alternatives and why they were rejected:
- **ESPN box score pages** render client-side; a fetch returns an empty page.
  Their JSON feed is not reachable from this environment.
- **NFL.com game center** also renders client-side and hides scores.

The Game Book is a static PDF published per game, linked from NFL.com game
center pages. Its URLs are opaque hashes and cannot be constructed — locate each
week's games by search. Budget time for 14–16 lookups per week.

The Game Book provides everything the scoring system needs: individual stat
lines, a scoring summary giving **every touchdown with its yardage**, field goal
distances, final scores for points allowed, and interception returns.

### Two rules that are easy to get wrong

**Sacks: the box score table is authoritative.** Game Books have been observed
disagreeing with their own play-by-play on sacks. Use the summary table and
ignore the play-by-play. This is a settled decision — do not re-litigate it
weekly.

**"Long" is not "long touchdown."** A player's long-reception column says
nothing about whether his touchdown was long. A 50-yard catch and a 13-yard
touchdown in the same game is a real pattern. `td_50plus` must come from the
**scoring summary**, never from a long-yardage column.

### Filling the raw file

Copy `weeks/_TEMPLATE.csv` to `weeks/raw-weekNN.csv` and fill one row per
tracked player who had a game. Columns a position does not use stay blank.

`status` is blank or `active` for a normal week; `BYE`, `DNP`, `IR`,
`INACTIVE`, `OUT`, or `SUSPENDED` otherwise. **Never put text in a numeric
column** — the scoring engine will reject the run and name the offending column,
which is the intended behavior.

`td_50plus` is **per player, not per play**: a 58-yard touchdown pass is a `1`
for the passer and a `1` for the receiver, since both earn the bonus.

Pull on **Tuesday** unless told otherwise, so Sunday-night and Monday stat
corrections have settled.

---

## 5. Running a Week

```
python3 run_week.py 6 weeks/raw-week06.csv
python3 build_cumulative.py
```

`run_week.py` scores every row and writes six per-position files, each pruned to
that position's own stat columns plus a trailing `points` column. Raw stats stay
in the output, so a later scoring change is re-runnable without re-pulling.

`build_cumulative.py` regenerates all six cumulative files from whatever weekly
files exist. It is a full rebuild, not an append — a corrected week-4 stat
therefore propagates to the totals automatically.

Run both test suites after any change to scoring or the pipeline:

```
python3 test_scoring.py && python3 test_cumulative.py
```

---

## 6. Scoring and Summary Rules

All point values live in `scoring.json`. Nothing is hard-coded in `score.py`. A
mid-season rule change means editing the JSON and re-running every week.

Decisions already settled, recorded so they are not re-asked:

- Yardage is continuous at 0.01 resolution — 87 rushing yards is 8.7, not 8.
- Yardage bonuses: **highest tier only** within each group. Passing bonuses and
  rush/receiving bonuses are separate groups and **do stack**, so a QB can earn
  both in one game.
- The 50+ yard touchdown bonus pays **every player credited on the play** —
  passer and receiver both. Exactly 50 yards qualifies.
- No penalty for lost fumbles, missed field goals, or missed extra points.
- A defense allowing 21+ points scores 0 from that parameter, never negative.
- Interception return yards always score. Fumble return yards score **only**
  when the return ends in a touchdown.
- Special teams return touchdowns pay the returner; the defense gets nothing.

Cumulative summary columns:

- **Average Points Per Game** divides by **games actually played**. Byes and
  inactive weeks are excluded entirely, never counted as zeros.
- **Standard Deviation** is **sample** (n−1), over the same active weeks. Blank
  when fewer than two games — a 0 there would wrongly read as perfect
  consistency.
- Missed weeks show their status label (`BYE`, `IR`) rather than a number. This
  is safe because cumulative files are only ever written, never read back as
  input. Do not hand-edit them.

Sorting: weekly files put active players first, then inactive, each group
alphabetical by "Last, First". Cumulative files sort by total points descending.

---

## 7. GitHub Updates

Files are edited directly via git commit and push. Updates are **batched at the
user's discretion**, never pushed automatically.

- Keep a running log of confirmed changes as the session progresses.
- Push only on an explicit go-ahead.
- Commit **only the files that actually changed**, with a clear message.
- If a session appears to be wrapping up, proactively flag any confirmed-but-
  unpushed changes and ask whether to push before ending.

**Push access:** pushing is authenticated through the Claude GitHub App
installation. **Do not ask the user for a personal access token** — none is
needed, and asking invites a credential that then has to be rotated for nothing.

If a push is refused with a 403 saying Claude lacks GitHub access to this repo,
the usual cause is that the repo is not in *this session's* authorised set. That
is per-session and separate from the app installation. If the session offers a
tool to attach a repository (`add_repo` or equivalent), call it for
`stat2883/Football` with push access, then retry the push once. Cloning and
reading work without this; only pushing needs it.

If a push is still refused after that, report the error verbatim rather than
working around it. The remedies are installing the Claude GitHub App at
`github.com/apps/claude/installations/select_target`, or reconnecting GitHub at
`claude.ai/customize/connectors`.

If a token is ever supplied anyway, it must **never** be committed, must be
redacted from any command output, and should be rotated afterwards.

**Git identity:** commits are always authored as
`stat2883 <stat2883@users.noreply.github.com>`. Set this before the first commit
of any session — do not ask, and never substitute a different name or invent an
email address.

---

## 8. General

- Never fabricate a statistic. If a Game Book cannot be located or a figure
  cannot be confirmed, leave the cell blank and say which player and which stat
  is missing, rather than estimating.
- Flag arithmetic inconsistencies when noticed rather than papering over them.
- Do not commit throwaway or example data to the repo. Use a scratch directory
  for demonstrations.
- Spreadsheets for the user to read are generated on request as `.xlsx` from the
  CSVs; the CSVs remain the system of record.
