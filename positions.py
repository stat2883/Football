"""Per-position stat schemas and name handling shared by the weekly scripts."""

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
# Surname particles that belong with the following word ("St. Brown", "Van Noy").
PARTICLES = {"st", "van", "von", "de", "del", "la", "le", "da", "di", "mc"}

# Stat columns carried in each position's weekly file. Identity columns
# (name, team, status) and the trailing points column are added separately.
SCHEMAS = {
    "QB": ["pass_yds", "pass_td", "pass_2pt", "int_thrown",
           "rush_yds", "rush_td", "rush_2pt", "td_50plus"],
    "RB": ["rush_yds", "rush_td", "rush_2pt",
           "rec", "rec_yds", "rec_td", "rec_2pt", "td_50plus", "st_ret_td"],
    "K":  ["fg_0_39", "fg_40_49", "fg_50_59", "fg_60plus", "xp_made"],
    "DEF": ["def_int", "def_sack", "def_fum_rec", "def_safety", "def_td",
            "def_int_ret_yds", "def_fum_ret_td_yds", "def_td_50plus",
            "pts_allowed"],
}
SCHEMAS["WR"] = SCHEMAS["RB"]
SCHEMAS["TE"] = SCHEMAS["RB"]

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

# Status values meaning the player did not play. Compared case-insensitively.
# These weeks are excluded from games played, average, and standard deviation.
INACTIVE_STATUSES = {"bye", "dnp", "ir", "inactive", "out", "suspended"}


def split_name(full_name):
    """'Amon-Ra St. Brown' -> ('St. Brown', 'Amon-Ra').

    Handles generational suffixes and two-word surname particles. Returns
    (last, first); first is '' for single-token names such as team defenses.
    """
    parts = full_name.split()
    if len(parts) == 1:
        return full_name, ""

    suffix = []
    while len(parts) > 1 and parts[-1].lower().rstrip(".") in SUFFIXES:
        suffix.insert(0, parts.pop())

    if len(parts) > 2 and parts[-2].lower().rstrip(".") in PARTICLES:
        last = " ".join(parts[-2:])
        first = " ".join(parts[:-2])
    else:
        last = parts[-1]
        first = " ".join(parts[:-1])

    if suffix:
        last = f"{last} {' '.join(suffix)}"
    return last, first


def display_name(last, first):
    """'St. Brown', 'Amon-Ra' -> 'St. Brown, Amon-Ra'. No comma when no first."""
    last = (last or "").strip()
    first = (first or "").strip()
    return f"{last}, {first}" if first else last


def is_inactive(status):
    return (status or "").strip().lower() in INACTIVE_STATUSES


def sort_key(row):
    """Active players first, then alphabetical by 'Last, First'.

    Inactive players (bye, injury, DNP) fall to the bottom, sorted the same way.
    """
    return (is_inactive(row.get("status")), display_name(
        row.get("last_name"), row.get("first_name")).lower())
