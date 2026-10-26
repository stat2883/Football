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
test_parse_week.py       74 checks on the Game Book reading, one per trap
fetch_week.py            downloads a week's Game Book PDFs and extracts text
fetch_schedule.py        downloads a season's schedule (run once per season)
parse_week.py            Game Books -> the raw weekly file
schedule-2026.csv        every regular-season game; tells a bye from an unpulled game
weeks/_TEMPLATE.csv      blank header row for a raw weekly pull
weeks/status-overrides.csv  why a player absent from the Game Book did not play
gamebooks/weekNN/        downloaded Game Books (not committed)
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
center pages. It provides everything the scoring system needs: individual stat
lines, a scoring summary giving **every touchdown with its yardage**, field goal
distances, final scores for points allowed, interception returns, and a
per-player defensive table with sacks, interceptions, forced fumbles and
recoveries.

### Downloading them

```
python3 fetch_week.py 7
```

This does the whole thing: reads the week's schedule page for every game slug,
scrapes each game page for its Game Book PDF link, downloads all of them, and
extracts each to fixed-layout text with `pdftotext`. Output lands in
`gamebooks/weekNN/`.

Games whose Game Book has not been published yet are reported as **PENDING**
rather than failing. Re-running skips what is already downloaded and collects
only the new ones, which is how a partial week (§4, Partial weeks) is topped up.

**This requires `www.nfl.com` and `static.www.nfl.com` to be allowed under
Settings > Capabilities on claude.ai.** If downloads fail with a 403 CONNECT
error, that allowance is missing or has been removed — tell the user rather than
trying to work around it.

Do **not** use the web fetch tool for Game Book PDFs. It only accepts URLs that
appear in search results, and recent games are not indexed, so it will fail for
exactly the games being pulled. The shell has no such restriction.

Sources evaluated and rejected:
- **ESPN box score pages** render client-side; a fetch returns an empty page.
- **NFL.com game center** also renders client-side and hides scores. It is still
  used to locate the PDF link, which is present in the raw HTML.
- **Pro-Football-Reference** has good offensive stats and scoring summaries, but
  hides its defensive and return tables in HTML comments, so they come back
  empty. Unusable as a sole source with team defenses on the list.

### Three rules that are easy to get wrong

**Sacks: the box score table is authoritative.** Game Books have been observed
disagreeing with their own play-by-play on sacks. Use the summary table and
ignore the play-by-play. This is a settled decision — do not re-litigate it
weekly.

Take the team's sack count from that table's **Total** row rather than adding
up the player rows. An unattributed sack is carried on a separate `Team Sacks`
line that no player row reflects, so a sum silently comes up short. Kansas City
in week 1: Total said 4, the player rows added to 3, and the team summary's
`Times thrown` confirmed 4. That same play-by-play narrated five.

**A touchdown can have no yardage.** A fumble recovered in the opponent's end
zone covers no distance, so it appears as `G.Halton fumble recovery in end
zone` with none of the usual `N yd. fumble return` wording — easy to skip when
scanning for touchdowns. Whether it belongs to the defense is settled by that
team's FUMBLES table: an `OPP-REC` touchdown is a defensive score worth 6; an
`OWN-REC` touchdown is a player falling on his own team's fumble, which is an
offensive score and credits the defense with nothing.

**"Long" is not "long touchdown."** A player's long-reception column says
nothing about whether his touchdown was long. A 50-yard catch and a 13-yard
touchdown in the same game is a real pattern. `td_50plus` must come from the
**scoring summary**, never from a long-yardage column.

### Reading a Game Book into the raw file

The extracted text is fixed-layout. Tables are **two-column: visitor on the
left, home on the right**, sharing one header line. Track which side is which
team — mixing them up silently assigns stats to the wrong players.

Sections and what to take:

| Section | Columns used |
|---|---|
| `RUSHING` | YDS → `rush_yds`, TD → `rush_td` |
| `PASSING` | YDS → `pass_yds`, TD → `pass_td`, IN → `int_thrown` |
| `PASS RECEIVING` | REC → `rec`, YDS → `rec_yds`, TD → `rec_td` |
| `Scoring Plays` | every TD's yardage → `td_50plus`; FG distances → kicker buckets |
| `Final Defensive Statistics` | SK, IN, FF, FR per player |
| `FINAL SCORE` | opponent's score → `pts_allowed` for that defense |

Rules learned from the first trial run:

- **Sack yardage is not rushing.** A quarterback's sacks appear in the PASSING
  table as `SK/YD`. They are not entered anywhere — this scoring system has no
  sack penalty for the quarterback — and must never be recorded as rush yards.
- **Use gross passing yards from the PASSING table, not net.** The team summary
  further down lists `NET YARDS PASSING`, which subtracts sack yardage. In the
  trial game the quarterback's table figure was 274 while net read 264. Take the
  per-player PASSING table value; the net figure is a team total and is wrong
  for scoring.
- **A quarterback absent from the RUSHING table has no rush yards**, even
  though he was sacked. Leave the column blank.
- **Negative rushing yards are real and they subtract.** Quarterbacks kneeling
  and receivers losing yards on end-arounds both show up; record the negative
  value as given.
- **Non-running-backs get carries.** Receivers appear in the RUSHING table.
  Their rows use the same schema, so fill both rush and receiving columns.
- **`TAR` (targets) is not used** by this scoring system. Ignore it.
- **Names are abbreviated** as initial-plus-surname (`A.St. Brown`,
  `J.Williams`). Resolve them against `players.csv` using surname **and team**;
  one game may contain two different players sharing an initial and surname on
  opposite sides.
- **Initials get lengthened to break ties within a team.** Jacksonville carried
  both `Bri.Thomas` and `Bry.Thomas` in week 1. Match the abbreviation as a
  *prefix of the first name*, not merely its first letter, or the stat line
  lands on the wrong player — and a player whose initial was lengthened will
  look absent if only the single letter is searched for.
- **A lateral reads `pass play by`, not `pass from`.** In week 3 Purdy threw
  two yards to Evans, who lateraled to Samuel for eighty more, and the summary
  read `D.Samuel 82 yd. pass play by B.Purdy`. The Game Book still credits the
  quarterback with the passing touchdown, so he takes the 50+ bonus. The
  intermediate receiver is credited only with his own short reception and takes
  no bonus, having scored nothing.
- **`td_50plus` comes from the Scoring Plays section only.** In the trial game
  the longest touchdown was 25 yards, so every value was 0 — despite a 40-yard
  reception appearing in the LG column.

### Filling the raw file

```
python3 parse_week.py 6
```

`parse_week.py` reads every Game Book in `gamebooks/weekNN/`, resolves each
tracked player against it and writes `weeks/raw-weekNN.csv`. It implements
every rule in this section, and `test_parse_week.py` asserts each of them
against the real Game Book fragment it came from, so they survive a rewrite.
Read the rules anyway: they are what the output has to be checked against when
a figure looks wrong, and a new Game Book quirk will need the same judgement
that produced them.

The script cross-checks itself against each document's own team totals — sacks
against `Times thrown`, interceptions against what the opponent threw, fumble
recoveries against what the opponent lost, and the scoring plays against the
final score — and reports any scoring play whose wording it does not recognise
rather than dropping it silently. That last check is what surfaced the week-5
end-zone fumble recovery. It exits non-zero when anything needs a human, so a
clean run is a positive signal rather than merely the absence of a crash.

Doing it by hand instead: copy `weeks/_TEMPLATE.csv` to `weeks/raw-weekNN.csv`
and fill one row per tracked player whose game has been pulled. Columns a
position does not use stay blank.

**`status` is mandatory on every row.** Use `active` for a game played, or
`BYE`, `DNP`, `IR`, `INACTIVE`, `OUT`, `SUSPENDED`. A blank status is rejected,
because it cannot be told apart from a game not yet pulled.

**Absent from the Game Book is not the same as inactive.** The Not Active list
names players who dressed and did not play; a player on IR, on the
Commissioner's Exempt List or otherwise off the gameday roster appears nowhere
in the document at all — not in the lineup, the substitutions, Did Not Play or
Not Active. He still needs a status, and the Game Book cannot supply one.
Confirm the reason outside it and record `IR`, `OUT` or `SUSPENDED`; do not
guess between them, and do not leave the row as `active`, which would score the
player a real 0.00 and drag his average down for a game he was ineligible for.
Every non-active status is excluded from games played alike, so the choice
affects the displayed label rather than any arithmetic.

Record the answer in `weeks/status-overrides.csv`
(`name,first_week,last_week,status,note`) rather than editing the raw file,
because `parse_week.py` rebuilds that file from the Game Books and a hand edit
is silently lost on the next run — which is exactly how Josh Jacobs briefly
became a scored 0.00 in week 1. An empty `last_week` means still out. A player
the Game Book *does* list as inactive is explained by the document, so that
always wins over an override.

Until an absence is explained, the row is written with a **blank status** on
purpose: `run_week.py` refuses blanks, which fails loudly instead of inventing
a zero.

**Never put text in a numeric column** — the scoring engine will reject the run
and name the offending column, which is the intended behavior.

### Byes and the schedule

`schedule-2026.csv` holds every regular-season game, downloaded once by
`fetch_schedule.py` and committed. It exists because a team with no Game Book
is in one of two completely different situations, and the gamebooks directory
cannot tell them apart:

- **not in the schedule that week** — a bye. The player gets a row with status
  `BYE`, which is excluded from games played.
- **in the schedule but not downloaded** — not pulled yet. The player gets **no
  row at all**, which is what lets the week be topped up later.

Confusing the two is quiet and damaging in both directions: a real bye written
as "not pulled" vanishes from the file, and an early pull written as a bye
permanently drops a game that was actually played. `parse_week.py` reports the
scheduled teams whose Game Book is still missing after every run, so a partial
week names itself.

With no schedule file the script assumes neither, reports it, and leaves the
rows out. Regenerate with `python3 fetch_schedule.py --season 2027` at the
start of a new season; it reads team names from the Game Books on disk, so run
`fetch_week.py 1` first.

### Partial weeks

A week can be pulled before all its games are played. The rule is simply:

- **No row** for a player → that game has not been pulled yet.
- **Row present** (always with a status) → pulled; leave it alone.

To top up later, append rows for the newly completed games to the same
`raw-weekNN.csv` and re-run `run_week.py` and `build_cumulative.py`. Both
rebuild from the raw file, so already-pulled players are not re-fetched and
nothing is double-counted.

`run_week.py` prints a **STILL TO PULL** list after every run, broken down by
position, naming exactly which players have no row yet. Use that list rather
than asking the user to remember which games were covered.

If the user asks for a partial pull, do not ask them to specify what was
already fetched — the raw file is the record.

`td_50plus` is **per player, not per play**: a 58-yard touchdown pass is a `1`
for the passer and a `1` for the receiver, since both earn the bonus.

**Pulls happen on demand only.** There is no schedule and nothing runs
automatically; a week is pulled when the user asks for it.

When the user does ask, note that stat corrections from Sunday night and Monday
are usually settled by **Tuesday**. If asked to pull a week earlier than that,
proceed as asked but mention that late corrections may follow — do not refuse
or delay.

---

## 5. Running a Week

```
python3 fetch_week.py 6
python3 parse_week.py 6
python3 run_week.py 6 weeks/raw-week06.csv
python3 build_cumulative.py
```

`run_week.py` scores every row and writes six per-position files, each pruned to
that position's own stat columns plus a trailing `points` column. Raw stats stay
in the output, so a later scoring change is re-runnable without re-pulling.

`build_cumulative.py` regenerates all six cumulative files from whatever weekly
files exist. It is a full rebuild, not an append — a corrected week-4 stat
therefore propagates to the totals automatically.

Run all three test suites after any change to scoring or the pipeline:

```
python3 test_scoring.py && python3 test_cumulative.py && python3 test_parse_week.py
```

---

## 6. Scoring and Summary Rules

All point values live in `scoring.json`. Nothing is hard-coded in `score.py`. A
mid-season rule change means editing the JSON and re-running every week.

Decisions already settled, recorded so they are not re-asked:

- Yardage is continuous at 0.01 resolution — 87 rushing yards is 8.7, not 8.
- **Negative yardage produces negative points.** It is not floored at zero. A
  quarterback kneeling out the clock for −1 rushing yard scores −0.1.
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
