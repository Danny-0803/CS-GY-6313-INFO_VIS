"""
Downloads every raw file into data/raw/.
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
NY = "https://data.ny.gov/resource"
S = requests.Session()
if os.environ.get("SOCRATA_APP_TOKEN"):
    S.headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]


def months(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y}-{m:02d}-01T00:00:00", f"{ny}-{nm:02d}-01T00:00:00"
        y, m = ny, nm


def get_csv(url: str, params: dict) -> pd.DataFrame:
    for attempt in range(6):
        r = S.get(url, params=params, timeout=300)
        if r.ok:
            return pd.read_csv(io.StringIO(r.text))
        print(f"   HTTP {r.status_code}, retrying ({r.text[:120]})")
        time.sleep(5 * (attempt + 1))
    sys.exit(f"Failed: {url} {params}")


def monthly(url, select, group, order, date_field, span, extra_where=None):
    frames = []
    for a, b in months(*span):
        where = f"{date_field} >= '{a}' AND {date_field} < '{b}'"
        if extra_where:
            where += f" AND {extra_where}"
        df = get_csv(url, {"$select": select, "$where": where, "$group": group, "$order": order, "$limit": 50000})
        if len(df) >= 50000:
            sys.exit(f"Query for {a} hit the 50,000 row limit; split it further.")
        print(f"   {a[:7]}: {len(df):,} rows")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


END = (2026, 10)
JOBS = {
    # D1 MTA Congestion Relief Zone Vehicle Entries (t6yz-b64h)
    "crz_daily": lambda: monthly(
        f"{NY}/t6yz-b64h.csv",
        "toll_date,detection_group,detection_region,vehicle_class,time_period,"
        "sum(crz_entries) as crz_entries,sum(excluded_roadway_entries) as excluded_entries",
        "toll_date,detection_group,detection_region,vehicle_class,time_period",
        "toll_date,detection_group,vehicle_class,time_period", "toll_date", (2025, 1, *END)),
    "crz_hourly": lambda: monthly(
        f"{NY}/t6yz-b64h.csv",
        "toll_date,hour_of_day,day_of_week,detection_group,"
        "sum(crz_entries) as crz_entries,sum(excluded_roadway_entries) as excluded_entries",
        "toll_date,hour_of_day,day_of_week,detection_group",
        "toll_date,hour_of_day,detection_group", "toll_date", (2025, 1, *END)),
    "crz_10min_cars": lambda: monthly(
        f"{NY}/t6yz-b64h.csv",
        "toll_10_minute_block,time_period,sum(crz_entries) as crz_entries,"
        "sum(excluded_roadway_entries) as excluded_entries",
        "toll_10_minute_block,time_period", "toll_10_minute_block", "toll_date", (2025, 1, *END),
        extra_where="vehicle_class = '1 - Cars, Pickups and Vans'"),
    # D2 MTA Bridges and Tunnels Hourly Crossings (ebfx-2m7v)
    "bt_daily": lambda: monthly(
        f"{NY}/ebfx-2m7v.csv",
        "date,facility,direction,vehicle_class_category,sum(traffic_count) as traffic_count",
        "date,facility,direction,vehicle_class_category",
        "date,facility,direction,vehicle_class_category", "date", (2019, 1, *END)),
    # D3 MTA CBD Bus Speeds (r6db-kkzj)
    "bus_speeds_hourly": lambda: get_csv(f"{NY}/r6db-kkzj.csv", {
        "$select": "month,cbd_relation,day_type,hour_of_day,time_period,"
                   "sum(sum_mileage) as miles,sum(sum_time) as hours,count(*) as route_rows",
        "$group": "month,cbd_relation,day_type,hour_of_day,time_period",
        "$order": "month,cbd_relation,day_type,hour_of_day", "$limit": 50000}),
    "bus_speeds_route_month": lambda: get_csv(f"{NY}/r6db-kkzj.csv", {
        "$select": "month,route_id,route_type,cbd_relation,day_type,sum(sum_mileage) as miles,sum(sum_time) as hours",
        "$group": "month,route_id,route_type,cbd_relation,day_type",
        "$order": "month,route_id,cbd_relation,day_type", "$limit": 500000}),
    # D4 MTA Subway Hourly Ridership (wujg-7c2s for 2020-2024, 5wq4-mkjj for 2025 on)
    "subway_daily": lambda: pd.concat([
        monthly(f"{NY}/{uid}.csv",
                "station_complex_id,station_complex,borough,latitude,longitude,"
                "date_trunc_ymd(transit_timestamp) as ride_date,sum(ridership) as ridership",
                "station_complex_id,station_complex,borough,latitude,longitude,ride_date",
                "ride_date,station_complex_id", "transit_timestamp", span)
        for uid, span in [("wujg-7c2s", (2023, 1, 2024, 12)), ("5wq4-mkjj", (2025, 1, *END))]], ignore_index=True),
    # Supporting: MTA Vehicle Miles Traveled in the CBD (jbxx-kxff) and old taxi speeds (6p29-6xqn)
    "vmt_monthly": lambda: get_csv(f"{NY}/jbxx-kxff.csv", {"$limit": 5000, "$order": "date,area"}),
    "taxi_speeds": lambda: get_csv(f"{NY}/6p29-6xqn.csv", {"$select": "month,zone,zonal_speed", "$order": "month,zone", "$limit": 5000}),
}


def fetch_geofence():
    # D5 MTA Central Business District Geofence (srxy-5nxn)
    r = S.get(f"{NY}/srxy-5nxn.geojson", params={"$limit": 100}, timeout=120)
    r.raise_for_status()
    (RAW / "cbd_geofence.geojson").write_text(r.text, encoding="utf-8")
    print("   saved cbd_geofence.geojson")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or [*JOBS, "cbd_geofence"]
    for name in wanted:
        print(f"== {name}")
        if name == "cbd_geofence":
            fetch_geofence()
            continue
        df = JOBS[name]()
        # the subway file is about 60 MB, so we save it compressed for GitHub
        out = RAW / (f"{name}.csv.gz" if name == "subway_daily" else f"{name}.csv")
        df.to_csv(out, index=False)
        print(f"   saved {out.name} ({len(df):,} rows)")
