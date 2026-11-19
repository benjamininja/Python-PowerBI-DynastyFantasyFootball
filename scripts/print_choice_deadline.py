"""Print the SQL statement that sets one choice deadline (ADR-0025 decision 4).

    print_choice_deadline.py --season SEASON_ID --kind resign|fa_keep --date YYYY-MM-DD

The instant is the end of the given day in America/New_York, 23:59:59, printed
in UTC. The script takes no clock time. It prints one INSERT and connects to
nothing: the owner pastes the statement in the Supabase SQL editor. On a key
that is already there the statement changes `deadline_at` only where the stored
instant is still later than the database's clock, so it never moves a deadline
that has passed; the trigger on `ops.choice_deadline` refuses the same thing
for every role. The output holds no name and no secret.
"""
import argparse
import re
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")
END_OF_DAY = time(23, 59, 59)
KINDS = ("resign", "fa_keep")
SEASON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
TABLE = "ops.choice_deadline"


def parse_day(text: str) -> date:
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"--date is not a YYYY-MM-DD date: {text!r}") from None
    if day.isoformat() != text:
        raise ValueError(f"--date is not a YYYY-MM-DD date: {text!r}")
    return day


def deadline_instant(day: date) -> datetime:
    """23:59:59 on `day` in America/New_York, as a UTC datetime."""
    return datetime.combine(day, END_OF_DAY, tzinfo=ZONE).astimezone(timezone.utc)


def statement(season_id: str, kind: str, day: date) -> str:
    if not SEASON_ID.match(season_id):
        raise ValueError(f"--season is not a season id: {season_id!r}")
    if kind not in KINDS:
        raise ValueError(f"--kind is not one of {', '.join(KINDS)}: {kind!r}")
    instant = deadline_instant(day).strftime("%Y-%m-%d %H:%M:%S+00")
    return (f"INSERT INTO {TABLE} (season_id, choice_kind, deadline_at) "
            f"VALUES ('{season_id}', '{kind}', timestamptz '{instant}') "
            f"ON CONFLICT (season_id, choice_kind) DO UPDATE SET deadline_at = EXCLUDED.deadline_at "
            f"WHERE {TABLE}.deadline_at > clock_timestamp();")


def main(argv=None, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", required=True, help="the season_id of dim_season the choice is made in")
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--date", required=True, help="the deadline day, YYYY-MM-DD")
    args = ap.parse_args(argv)
    try:
        sql = statement(args.season, args.kind, parse_day(args.date))
    except ValueError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    out(sql)
    return 0


if __name__ == "__main__":
    sys.exit(main())
