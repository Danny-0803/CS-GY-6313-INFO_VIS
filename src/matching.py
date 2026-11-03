"""
How each 2025-26 day is matched to a 2024 day.
- 2025 dates go back 364 days and 2026 dates go back 728 days, so the weekday always matches.
- A holiday is matched to the same holiday in 2024. We count federal holidays plus Christmas Eve, New Year's Eve and the day after Thanksgiving.
- If a normal day would land on a 2024 holiday, we go one more week back (or one week forward if that is a holiday too).
  The match always stays in 2024, so Dec 30, 2025 goes two weeks back, to Dec 17, 2024.
- A 2024 day can be used twice when a nearby day was moved off a holiday. Both sides still have the same number of days.
- Each pair gets a match_type so it can be filtered out later.
Monthly data (bus speeds, vehicle miles) is compared with the same month of 2024.
"""
from __future__ import annotations

from datetime import date, timedelta

import holidays
import pandas as pd

BASE_YEAR = 2024


def special_days(years=(2024, 2025, 2026)) -> dict[date, str]:
    out: dict[date, str] = {}
    us = holidays.US(years=list(years))
    for d, name in us.items():
        out[d] = name.replace(" (observed)", "") + (" (observed)" if "observed" in name else "")
    for y in years:
        out[date(y, 12, 24)] = "Christmas Eve"
        out[date(y, 12, 31)] = "New Year's Eve"
        thanksgiving = [d for d, n in us.items() if d.year == y and n.startswith("Thanksgiving")][0]
        out[thanksgiving + timedelta(days=1)] = "Day after Thanksgiving"
    return out


SPECIAL = special_days()


def _base_key(name: str) -> str:
    return name.replace(" (observed)", "")


def match_day(d: date) -> tuple[date, str]:
    """Returns (matched 2024 date, match_type) for a 2025 or 2026 date."""
    if d.year not in (2025, 2026):
        raise ValueError("only 2025 and 2026 dates are matched")
    weeks = 52 * (d.year - BASE_YEAR)
    shifted = d - timedelta(days=7 * weeks)

    if d in SPECIAL:
        key = _base_key(SPECIAL[d])
        same = [b for b, n in SPECIAL.items() if b.year == BASE_YEAR and _base_key(n) == key]
        if same:
            # use the actual holiday, not the observed date, if both exist
            same.sort(key=lambda b: "observed" in SPECIAL[b])
            return same[0], "holiday_to_holiday"
        return shifted, "same_weekday"

    if shifted in SPECIAL:
        # one week back, then one week forward, then two weeks back; always a normal day in 2024
        for step in (-7, 7, -14):
            near = shifted + timedelta(days=step)
            if near not in SPECIAL and near.year == BASE_YEAR:
                return near, "shifted_off_holiday"

    return shifted, "same_weekday"


def match_table(dates) -> pd.DataFrame:
    rows = []
    for d in dates:
        d = pd.Timestamp(d).date()
        b, kind = match_day(d)
        rows.append({
            "target_date": d, "target_weekday": d.strftime("%a"),
            "target_holiday": SPECIAL.get(d, ""),
            "baseline_date": b, "baseline_weekday": b.strftime("%a"),
            "baseline_holiday": SPECIAL.get(b, ""),
            "days_apart": (d - b).days, "match_type": kind,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    demo = ["2025-01-05", "2025-03-12", "2025-06-18", "2025-06-19", "2025-07-03",
            "2025-07-04", "2025-11-27", "2025-11-28", "2025-12-25", "2026-01-01",
            "2026-01-19", "2026-03-04", "2026-07-03", "2026-09-15"]
    print(match_table(demo).to_string(index=False))
