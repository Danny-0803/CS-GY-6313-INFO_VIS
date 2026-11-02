"""
Builds the tables in data/processed/ from the files in data/raw/.
All comparisons stop at CUTOFF, the last full month that every source covers.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from matching import match_day

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

TOLL_START = pd.Timestamp("2025-01-05")
CUTOFF = pd.Timestamp("2026-09-30")  # last full month in every source
INTO_ZONE = {"Queens Midtown Tunnel": "Westbound to Manhattan",
             "Hugh L. Carey Tunnel": "Northbound to Manhattan"}


def raw(name: str) -> Path:
    """Path to data/raw/<name>.csv, or the .csv.gz version if that is what we have."""
    plain = RAW / f"{name}.csv"
    return plain if plain.exists() else RAW / f"{name}.csv.gz"


def save(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"  {name}.csv  {len(df):,} rows")
    return df


def pct(a, b):
    return np.where(b > 0, (a / b - 1) * 100, np.nan)


# matching
def matched_days(start=TOLL_START, end=CUTOFF) -> pd.DataFrame:
    rows = []
    for d in pd.date_range(start, end, freq="D"):
        b, kind = match_day(d.date())
        rows.append({"date": d, "baseline_date": pd.Timestamp(b), "match_type": kind})
    return pd.DataFrame(rows)


def compare_matched(series: pd.DataFrame, key_cols: list[str], value: str, days: pd.DataFrame) -> pd.DataFrame:
    """Adds the value from each row's matched 2024 day as a new column."""
    tgt = series.merge(days, on="date", how="inner")
    base = series.rename(columns={"date": "baseline_date", value: f"{value}_2024"})
    out = tgt.merge(base[["baseline_date", *key_cols, f"{value}_2024"]], on=["baseline_date", *key_cols], how="left")
    return out


# D1
def load_crz():
    crz = pd.read_csv(RAW / "crz_daily.csv", parse_dates=["toll_date"]).rename(columns={"toll_date": "date"})
    crz["total_entries"] = crz.crz_entries + crz.excluded_entries
    return crz


def flag_outage_days(daily_total: pd.Series, threshold=0.6) -> pd.Series:
    """Marks days below 60% of the normal level for that weekday (5-week median).
    These are storms or data gaps."""
    s = daily_total.sort_index()
    out = pd.Series(False, index=s.index)
    for wd in range(7):
        sub = s[s.index.dayofweek == wd]
        med = sub.rolling(5, center=True, min_periods=3).median()
        out.loc[sub.index] = sub < threshold * med
    return out


def q1_and_q3(crz: pd.DataFrame):
    print("Q1 / Q3: vehicle entries")
    d = crz[crz.date <= CUTOFF]

    daily = d.groupby(["date", "detection_group", "detection_region"], as_index=False)[
        ["crz_entries", "excluded_entries", "total_entries"]].sum()
    tot = daily.groupby("date").crz_entries.sum()
    flags = flag_outage_days(tot)
    daily["flag_low_day"] = daily.date.map(flags)
    save(daily, "q1_entries_daily_by_crossing")

    monthly = d.assign(month=d.date.dt.to_period("M").dt.to_timestamp()).groupby(
        ["month", "detection_group", "vehicle_class"], as_index=False).agg(
        days=("date", "nunique"), crz_entries=("crz_entries", "sum"))
    monthly["avg_daily_entries"] = (monthly.crz_entries / monthly.days).round(0)
    save(monthly, "q1_entries_monthly_by_crossing_class")

    hourly = pd.read_csv(RAW / "crz_hourly.csv", parse_dates=["toll_date"])
    hourly = hourly[hourly.toll_date <= CUTOFF]
    hourly["year"] = hourly.toll_date.dt.year
    jan_sep = hourly[hourly.toll_date.dt.month <= 9]
    by_day = jan_sep.groupby(["year", "toll_date", "day_of_week", "hour_of_day"], as_index=False).crz_entries.sum()
    heat = by_day.groupby(["year", "day_of_week", "hour_of_day"], as_index=False).crz_entries.mean()
    heat = heat.pivot_table(index=["day_of_week", "hour_of_day"], columns="year", values="crz_entries").reset_index()
    heat.columns = ["day_of_week", "hour_of_day", "avg_entries_2025", "avg_entries_2026"]
    heat["pct_change_2026_vs_2025"] = pct(heat.avg_entries_2026, heat.avg_entries_2025).round(1)
    heat[["avg_entries_2025", "avg_entries_2026"]] = heat[["avg_entries_2025", "avg_entries_2026"]].round(0)
    save(heat, "q1_heatmap_weekday_hour")

    # Q3: share of entries that stay on the free FDR Drive and West Side Highway
    m = d.assign(month=d.date.dt.to_period("M").dt.to_timestamp()).groupby(["month", "detection_group"], as_index=False)[
        ["crz_entries", "excluded_entries"]].sum()
    m["excluded_share_pct"] = (100 * m.excluded_entries / (m.crz_entries + m.excluded_entries)).round(2)
    save(m, "q3_excluded_share_monthly")

    # Q3: weekday car entries per 10 minutes, first 3 months vs latest 3 months
    ten = pd.read_csv(RAW / "crz_10min_cars.csv", parse_dates=["toll_10_minute_block"])
    ten["date"] = ten.toll_10_minute_block.dt.normalize()
    ten = ten[(ten.date <= CUTOFF) & (ten.date.dt.dayofweek < 5)]
    ten = ten[~ten.date.isin(flags[flags].index)]
    ten["clock"] = ten.toll_10_minute_block.dt.strftime("%H:%M")
    windows = {"Jan-Mar 2025": ("2025-01-05", "2025-03-31"), "Jul-Sep 2026": ("2026-07-01", "2026-09-30")}
    parts = []
    for label, (a, b) in windows.items():
        w = ten[(ten.date >= a) & (ten.date <= b)]
        g = w.groupby(["clock", "time_period"], as_index=False).crz_entries.mean()
        g["window"] = label
        parts.append(g)
    clock = pd.concat(parts)
    clock = clock.pivot_table(index=["clock", "time_period"], columns="window", values="crz_entries").reset_index()
    clock.columns.name = None
    clock = clock.rename(columns={"Jan-Mar 2025": "avg_car_entries_jan_mar_2025", "Jul-Sep 2026": "avg_car_entries_jul_sep_2026"}).round(1)
    save(clock, "q3_toll_clock_weekday_cars")
    return flags


# D2
def baseline(crz: pd.DataFrame):
    print("Baseline: bridges and tunnels (D2) vs zone entries (D1)")
    bt = pd.read_csv(RAW / "bt_daily.csv", parse_dates=["date"])

    # check that D1 and D2 agree for the two tunnels they share
    rows = []
    for fac, dirn in INTO_ZONE.items():
        d2 = bt[(bt.facility == fac) & (bt.direction == dirn)].groupby("date").traffic_count.sum()
        d1 = crz[crz.detection_group == fac].groupby("date").total_entries.sum()
        j = pd.concat([d1.rename("d1_zone_entries"), d2.rename("d2_crossings")], axis=1, join="inner")
        j = j[j.index <= CUTOFF]
        mth = j.resample("MS").sum()
        mth["ratio_d1_to_d2"] = (mth.d1_zone_entries / mth.d2_crossings).round(3)
        mth["facility"] = fac
        rows.append(mth.reset_index().rename(columns={"date": "month"}))
    check = pd.concat(rows)[["month", "facility", "d1_zone_entries", "d2_crossings", "ratio_d1_to_d2"]]
    save(check, "baseline_check_d1_vs_d2_monthly")

    # tunnels into the zone vs other MTA crossings, each day vs its matched 2024 day
    bt["group"] = np.where(bt.apply(lambda r: INTO_ZONE.get(r.facility) == r.direction, axis=1),
                           "MTA tunnels into the zone", None)
    other = ~bt.facility.isin(INTO_ZONE.keys())
    bt.loc[other, "group"] = "Other MTA crossings (not into the zone)"
    g = bt.dropna(subset=["group"]).groupby(["date", "group"], as_index=False).traffic_count.sum()
    days = matched_days()
    cmp = compare_matched(g, ["group"], "traffic_count", days)
    cmp["month"] = cmp.date.dt.to_period("M").dt.to_timestamp()
    mon = cmp.groupby(["month", "group"], as_index=False).agg(
        matched_days=("date", "count"), crossings=("traffic_count", "sum"), crossings_2024=("traffic_count_2024", "sum"))
    mon["pct_change_vs_2024"] = pct(mon.crossings, mon.crossings_2024).round(1)
    save(mon, "q1_baseline_tunnels_vs_other_monthly")

    # monthly totals since 2019, where the 2024 average month = 100
    lv = g.assign(month=g.date.dt.to_period("M").dt.to_timestamp()).groupby(["month", "group"], as_index=False).traffic_count.sum()
    lv = lv[lv.month <= CUTOFF]
    ref = lv[lv.month.dt.year == 2024].groupby("group").traffic_count.mean()
    lv["index_2024_avg_100"] = (100 * lv.traffic_count / lv.group.map(ref)).round(1)
    save(lv, "q1_crossings_since_2019_monthly")
    return mon


# bus speeds
def q2_bus():
    print("Q2: bus speeds")
    bus = pd.read_csv(RAW / "bus_speeds_hourly.csv", parse_dates=["month"])
    bus = bus[bus.month <= CUTOFF]
    m = bus.groupby(["month", "cbd_relation", "day_type"], as_index=False)[["miles", "hours"]].sum()
    m["avg_speed_mph"] = (m.miles / m.hours).round(2)
    base = m[m.month.dt.year == 2024].assign(cal_month=lambda x: x.month.dt.month)[["cal_month", "cbd_relation", "day_type", "avg_speed_mph"]]
    m["cal_month"] = m.month.dt.month
    m = m.merge(base.rename(columns={"avg_speed_mph": "speed_same_month_2024"}), on=["cal_month", "cbd_relation", "day_type"], how="left")
    m["pct_change_vs_2024"] = pct(m.avg_speed_mph, m.speed_same_month_2024).round(1)
    m.loc[m.month.dt.year < 2025, "pct_change_vs_2024"] = np.nan
    save(m.drop(columns="cal_month"), "q2_bus_speed_monthly")

    h = bus[(bus.day_type == "Weekday")].copy()
    h["year"] = h.month.dt.year
    h = h[h.month.dt.month <= 9]
    hp = h.groupby(["year", "cbd_relation", "hour_of_day"], as_index=False)[["miles", "hours"]].sum()
    hp["avg_speed_mph"] = (hp.miles / hp.hours).round(2)
    hp = hp.pivot_table(index=["cbd_relation", "hour_of_day"], columns="year", values="avg_speed_mph").reset_index()
    hp.columns = ["cbd_relation", "hour_of_day"] + [f"speed_jan_sep_{c}" for c in hp.columns[2:]]
    save(hp, "q2_bus_speed_weekday_by_hour")
    return m


# subway
def zone_polygon():
    gj = json.loads((RAW / "cbd_geofence.geojson").read_text())
    return unary_union([shape(f["geometry"]) for f in gj["features"]])


def q4_subway():
    print("Q4: subway ridership")
    sub = pd.read_csv(raw("subway_daily"), parse_dates=["ride_date"]).rename(columns={"ride_date": "date"})
    stations = sub.groupby("station_complex_id", as_index=False).agg(
        station_complex=("station_complex", "last"), borough=("borough", "last"),
        latitude=("latitude", "median"), longitude=("longitude", "median"))
    zone = prep(zone_polygon())
    def area(r):
        if zone.contains(Point(r.longitude, r.latitude)):
            return "Inside the zone"
        if r.borough == "Manhattan":
            return "Manhattan above 60th St"
        return "Outer boroughs"
    stations["area"] = stations.apply(area, axis=1)
    save(stations, "q4_stations_tagged")

    daily = sub.merge(stations[["station_complex_id", "area"]], on="station_complex_id")
    by_area = daily.groupby(["date", "area"], as_index=False).ridership.sum()
    days = matched_days()
    cmp = compare_matched(by_area, ["area"], "ridership", days)
    cmp["month"] = cmp.date.dt.to_period("M").dt.to_timestamp()
    mon = cmp.groupby(["month", "area"], as_index=False).agg(
        matched_days=("date", "count"), ridership=("ridership", "sum"), ridership_2024=("ridership_2024", "sum"))
    mon["pct_change_vs_2024"] = pct(mon.ridership, mon.ridership_2024).round(1)
    save(mon, "q4_subway_by_area_monthly")

    st = daily.groupby(["date", "station_complex_id"], as_index=False).ridership.sum()
    cmp_s = compare_matched(st, ["station_complex_id"], "ridership", days)
    cmp_s["year"] = cmp_s.date.dt.year
    cmp_s = cmp_s[cmp_s.date.dt.month <= 9]
    s = cmp_s.groupby(["station_complex_id", "year"], as_index=False).agg(
        ridership=("ridership", "sum"), ridership_2024=("ridership_2024", "sum"))
    s["pct_change_vs_2024"] = pct(s.ridership, s.ridership_2024).round(1)
    s = s.pivot_table(index="station_complex_id", columns="year", values=["ridership", "pct_change_vs_2024"]).reset_index()
    s.columns = ["station_complex_id"] + [f"{a}_jan_sep_{b}" for a, b in s.columns[1:]]
    s = stations.merge(s, on="station_complex_id", how="left")
    save(s, "q4_station_pct_change_map")
    return mon


def q4_placebo():
    """Same rule on 2024 vs 2023, before the toll. Shows how much subway counts
    moved on their own."""
    print("Q4 check: placebo 2024 vs 2023")
    sub = pd.read_csv(raw("subway_daily"), parse_dates=["ride_date"])
    stations = pd.read_csv(OUT / "q4_stations_tagged.csv")[["station_complex_id", "area"]]
    d = sub.merge(stations, on="station_complex_id").groupby(["ride_date", "area"]).ridership.sum()
    rows = []
    for day in pd.date_range("2024-01-07", "2024-12-31"):
        b = day - pd.Timedelta(days=364)
        for area in ("Inside the zone", "Outer boroughs"):
            if (day, area) in d.index and (b, area) in d.index:
                rows.append({"month": day.to_period("M").to_timestamp(), "area": area,
                             "ridership_2024": d[(day, area)], "ridership_2023": d[(b, area)]})
    p = pd.DataFrame(rows).groupby(["month", "area"], as_index=False).sum()
    p["pct_change_2024_vs_2023"] = pct(p.ridership_2024, p.ridership_2023).round(1)
    return save(p, "q4_placebo_2024_vs_2023_monthly")


def baseline_vmt():
    """Vehicle-miles index for the zone and the free excluded roadways, vs the same month of 2024."""
    print("Baseline check: vehicle miles traveled")
    v = pd.read_csv(RAW / "vmt_monthly.csv", parse_dates=["date"]).drop(columns=["year", "month"])
    v = v.rename(columns={"date": "month"})
    v = v[v.month <= CUTOFF]
    base = v[v.month.dt.year == 2024].assign(m=lambda x: x.month.dt.month)[["m", "area", "indexed_average_vmt"]]
    v["m"] = v.month.dt.month
    v = v.merge(base.rename(columns={"indexed_average_vmt": "index_same_month_2024"}), on=["m", "area"], how="left")
    v["pct_change_vs_2024"] = pct(v.indexed_average_vmt, v.index_same_month_2024).round(1)
    v.loc[v.month.dt.year < 2025, "pct_change_vs_2024"] = np.nan
    v["area"] = v.area.map({"CRZ": "Congestion Relief Zone", "ER": "Excluded roadways (FDR, West Side Hwy)"})
    return save(v.drop(columns="m"), "baseline_vmt_monthly")


def matching_coverage():
    days = matched_days()
    save(days, "matching_rule_all_days")
    print("   match types:", days.match_type.value_counts().to_dict())


# scorecard
def q7(bt_mon, bus_m, sub_mon, vmt=None):
    print("Q7: scorecard")
    rows = []
    if vmt is not None:
        for grp, role in [("Congestion Relief Zone", "zone"), ("Excluded roadways (FDR, West Side Hwy)", "comparison")]:
            for yr, last in ((2025, 9), (2026, 6)):
                x = vmt[(vmt.area == grp) & (vmt.month.dt.year == yr) & (vmt.month.dt.month <= last)]
                rows.append({"measure": "Vehicle miles (index)", "group": grp, "role": role,
                             "period": f"Jan-{'Sep' if last == 9 else 'Jun'} {yr}",
                             "pct_change_vs_2024": round(float(x.pct_change_vs_2024.mean()), 1)})
    def add(measure, group, comparison, df, val, base):
        for yr in (2025, 2026):
            x = df[(df.month.dt.year == yr) & (df.month.dt.month <= 9)]
            rows.append({"measure": measure, "group": group, "role": comparison,
                         "period": f"Jan-Sep {yr}" if yr == 2026 else "Jan-Sep 2025",
                         "pct_change_vs_2024": round(float((x[val].sum() / x[base].sum() - 1) * 100), 1)})
    for grp, role in [("MTA tunnels into the zone", "zone"), ("Other MTA crossings (not into the zone)", "comparison")]:
        add("Vehicle crossings", grp, role, bt_mon[bt_mon.group == grp], "crossings", "crossings_2024")
    for grp, role in [("Inside the zone", "zone"), ("Outer boroughs", "comparison")]:
        add("Subway entries", grp, role, sub_mon[sub_mon.area == grp], "ridership", "ridership_2024")
    w = bus_m[bus_m.day_type == "Weekday"]
    for grp, role in [("CBD", "zone"), ("Non-CBD", "comparison")]:
        x = w[w.cbd_relation == grp]
        for yr in (2025, 2026):
            y = x[(x.month.dt.year == yr) & (x.month.dt.month <= 9)]
            rows.append({"measure": "Weekday bus speed", "group": f"Bus segments {grp}", "role": role,
                         "period": f"Jan-Sep {yr}", "pct_change_vs_2024": round(float(y.pct_change_vs_2024.mean()), 1)})
    save(pd.DataFrame(rows), "q7_scorecard")


if __name__ == "__main__":
    matching_coverage()
    crz = load_crz()
    q1_and_q3(crz)
    bt_mon = baseline(crz)
    vmt = baseline_vmt()
    bus_m = q2_bus()
    sub_mon = q4_subway()
    q4_placebo()
    q7(bt_mon, bus_m, sub_mon, vmt)
