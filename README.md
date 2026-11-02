# The $9 Line: What Changed After NYC Started Congestion Pricing
Group: Kuch Bhi, Devansh Sharma and Darsh Shani.

CS-GY 6313 Information Visualization, NYU Tandon, Fall 2026.

On January 5, 2025, New York started charging most cars $9 to drive into Manhattan below 60th Street. We look at what changed after that: vehicle entries, bus speeds, how drivers time their trips around the price, and subway use. Each change is compared with a group outside the zone and with matched days in 2024. These comparisons are descriptive. We don't claim the toll alone caused any change.

Our audience is policymakers and the public in U.S. cities that are thinking about congestion pricing.

## Questions

- Q1. How have vehicle entries into the zone changed, by crossing, vehicle type and time of day?
- Q2. How have weekday bus speeds inside the zone changed compared with bus speeds outside it?
- Q3. Do drivers avoid the toll by timing trips around the 5 AM and 9 PM price changes, or by using the free FDR Drive and West Side Highway?
- Q4. How did subway entries inside the zone change compared with the outer boroughs, and how much of that trend was there before the toll?
- Q7. Comparing 2025 with 2026, which changes held up and which faded?
- "Not being covered" Q5 (where new subway riders come from) and Q6 (horn complaints and crashes).


## What's in this repo 
```
data/raw/          the downloaded data
data/processed/    tables made from the raw data
src/fetch_data.py  downloads the raw data
src/matching.py    matches each 2025-26 day to a 2024 day
src/process.py     makes the processed tables
```
## How to run it

You need Python 3.10 or newer.
```
pip install -r requirements.txt
python src/process.py       # rebuilds data/processed
python src/fetch_data.py    # optional: downloads data/raw again
```
The subway file is saved as `.csv.gz` to stay under GitHub's size limit. The scripts read it as is.

## Data
Each link below opens the dataset page.

| ID | Dataset                                    | Link                            |
|---|---|---|
| D1 | MTA Congestion Relief Zone Vehicle Entries | https://data.ny.gov/d/t6yz-b64h |
| D2 | MTA Bridges and Tunnels Hourly Crossings   | https://data.ny.gov/d/ebfx-2m7v |
| D3 | MTA Central Business District Bus Speeds   | https://data.ny.gov/d/r6db-kkzj |
| D4 | MTA Subway Hourly Ridership, 2020 to 2024  | https://data.ny.gov/d/wujg-7c2s |
| D4 | MTA Subway Hourly Ridership, 2025 on       | https://data.ny.gov/d/5wq4-mkjj |
| D5 | MTA Central Business District Geofence     | https://data.ny.gov/d/srxy-5nxn |
| S1 | MTA Vehicle Miles Traveled in the CBD      | https://data.ny.gov/d/jbxx-kxff |
| S2 | MTA CBD Taxi and For-Hire Vehicle Speeds   | https://data.ny.gov/d/6p29-6xqn |

## Processed tables

| File                                       | Question | Each row is |
|---|---|---|
| `matching_rule_all_days.csv`               | all      | a 2025-26 day and its matched 2024 day |
| `q1_entries_daily_by_crossing.csv`         | Q1       | one entry point on one day |
| `q1_entries_monthly_by_crossing_class.csv` | Q1       | one entry point, vehicle type and month |
| `q1_heatmap_weekday_hour.csv`              | Q1       | one weekday and hour |
| `q1_baseline_tunnels_vs_other_monthly.csv` | Q1       | one month and group, vs matched 2024 days |
| `q1_crossings_since_2019_monthly.csv`      | Q1       | one month and group, 2019 to 2026 |
| `baseline_check_d1_vs_d2_monthly.csv`      | baseline | one tunnel and month, D1 vs D2 |
| `baseline_vmt_monthly.csv`                 | baseline | one area and month |
| `q2_bus_speed_monthly.csv`                 | Q2       | one month, area and day type |
| `q2_bus_speed_weekday_by_hour.csv`         | Q2       | one area and hour |
| `q3_toll_clock_weekday_cars.csv`           | Q3       | one 10-minute block of the day |
| `q3_excluded_share_monthly.csv`            | Q3       | one entry point and month |
| `q4_stations_tagged.csv`                   | Q4       | one station and its area |
| `q4_subway_by_area_monthly.csv`            | Q4       | one area and month, vs matched 2024 days |
| `q4_placebo_2024_vs_2023_monthly.csv`      | Q4       | one area and month, 2024 vs 2023 |
| `q4_station_pct_change_map.csv`            | Q4       | one station |
| `q7_scorecard.csv`                         | Q7       | one measure, group and period |

## How days are matched

A 2025 day is compared with the day 364 days earlier, and a 2026 day with the day 728 days earlier, so the weekday is always the same. Holidays are matched to the same holiday in 2024. If a normal day would land on a 2024 holiday, we use the week before instead. Monthly data is compared with the same month in 2024. Everything stops at 30 September 2026.

## AI use

We used Claude and ChatGPT to help generate ideas and to grasp a clear explanation of the feedback. We also took help to figure out which dataset is better for each problem and how to tackle the the days matching.

