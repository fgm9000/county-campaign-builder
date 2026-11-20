"""Download NOAA, NWS and Census data and write data/counties.parquet and counties_meta.json.

Network and disk only; the logic lives in county_campaign_builder.county_data.
Needs CENSUS_API_KEY in the environment. The key is never written to disk or printed.
"""

import gzip
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
import polars as pl

from county_campaign_builder.county_data import (
    CENSUS_VARIABLES,
    HAIL_MIN_INCHES,
    STORM_YEARS,
    TROPICAL_EVENT_TYPES,
    WIND_MIN_KNOTS,
    build_county_table,
    parse_census,
    parse_storm_events,
    parse_zone_map,
    read_storm_events,
    years_label,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
OUTPUT_PARQUET = REPO_ROOT / "data" / "counties.parquet"
OUTPUT_META = REPO_ROOT / "data" / "counties_meta.json"

NOAA_RELEASE = "c20261118"
NOAA_URL = (
    "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
    "StormEvents_details-ftp_v1.0_d{year}_{release}.csv.gz"
)
ZONE_MAP_NAME = "bp16ap26.dbx"
ZONE_MAP_URL = f"https://www.weather.gov/source/gis/Shapefiles/County/{ZONE_MAP_NAME}"
CENSUS_URL = "https://api.census.gov/data/2024/acs/acs5"
CENSUS_KEY_VARIABLE = "CENSUS_API_KEY"
CENSUS_FIELDS = ["NAME", *CENSUS_VARIABLES]
DOWNLOAD_TIMEOUT_SECONDS = 300.0
CENSUS_TIMEOUT_SECONDS = 120.0
PARQUET_COMPRESSION: Literal["zstd"] = "zstd"

COLUMN_DEFINITIONS = {
    "fips": "5-digit county FIPS (state + county), text",
    "county_name": "Census county name, e.g. 'Dallas County, Texas'",
    "hail_reports_1in": "NOAA Hail event records with MAGNITUDE >= 1.0 inch, county rows only",
    "severe_wind_reports": "NOAA Thunderstorm Wind records with MAGNITUDE >= 50 knots, county rows",
    "tornado_events": "NOAA Tornado event records, county rows only",
    "tropical_events": (
        "NOAA Hurricane (Typhoon), Tropical Storm and Tropical Depression records; zone records "
        "count for every county the NWS zone covers"
    ),
    "years_covered": "Storm window, first-last calendar year",
    "median_year_built": "ACS B25035_001E, median year structure built",
    "households": "ACS B25003_001E, occupied housing units",
    "owner_occupied": "ACS B25003_002E, owner-occupied housing units",
    "owner_occupied_pct": "owner_occupied / households * 100, 2 decimals",
    "housing_units": "ACS B25002_001E, total housing units",
    "vacant_units": "ACS B25002_003E, vacant housing units",
    "vacancy_pct": "vacant_units / housing_units * 100, 2 decimals",
    "median_home_value_usd": "ACS B25077_001E, median value of owner-occupied units, USD",
    "owner_long_tenure_pct": (
        "ACS B25038 (_007E + _008E) / _002E * 100: owner-occupied units whose householder moved "
        "in before 2000, a proxy for long tenure and built-up equity"
    ),
    "free_and_clear_pct": (
        "ACS B25081_009E / _001E * 100: owner-occupied units without a mortgage (free and clear)"
    ),
}


def download_if_missing(url: str, target: Path) -> Path:
    """Download `url` to `target` unless the file already exists."""
    if target.exists():
        print(f"cached  {target.name}")
        return target
    print(f"fetch   {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as resp:
        resp.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in resp.iter_bytes():
                handle.write(chunk)
    partial.replace(target)
    return target


def fetch_census_rows() -> list[list[str]]:
    """Call the ACS API; errors are re-raised without the URL because it carries the key."""
    key = os.environ.get(CENSUS_KEY_VARIABLE)
    if not key:
        raise SystemExit(f"{CENSUS_KEY_VARIABLE} is not set")
    params = {"get": ",".join(CENSUS_FIELDS), "for": "county:*", "key": key}
    try:
        response = httpx.get(CENSUS_URL, params=params, timeout=CENSUS_TIMEOUT_SECONDS)
        response.raise_for_status()
        rows: list[list[str]] = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Census API answered HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"Census API call failed ({type(exc).__name__})") from None
    return rows


def load_storm_frame() -> pl.DataFrame:
    """Download (or reuse) the yearly NOAA files and stack them."""
    frames = []
    for year in STORM_YEARS:
        url = NOAA_URL.format(year=year, release=NOAA_RELEASE)
        path = download_if_missing(url, RAW_DIR / url.rsplit("/", 1)[1])
        frames.append(read_storm_events(gzip.decompress(path.read_bytes())))
    return pl.concat(frames)


def build_meta(table: pl.DataFrame) -> dict[str, Any]:
    """Describe sources, window, definitions and size of the generated table."""
    return {
        "generated_at": date.today().isoformat(),
        "county_count": table.height,
        "storm_years": years_label(STORM_YEARS),
        "sources": {
            "noaa_storm_events": NOAA_URL.format(year="<YEAR>", release=NOAA_RELEASE),
            "nws_zone_county_map": ZONE_MAP_URL,
            "census_acs5": f"{CENSUS_URL}?get={','.join(CENSUS_FIELDS)}&for=county:*",
        },
        "zone_map_version": ZONE_MAP_NAME,
        "census_vintage": "ACS 5-year 2020-2024",
        "rules": {
            "hail_min_inches": HAIL_MIN_INCHES,
            "wind_min_knots": WIND_MIN_KNOTS,
            "tropical_event_types": list(TROPICAL_EVENT_TYPES),
            "counting_unit": "event records deduplicated by EVENT_ID, not distinct storms",
            "zone_events": "a zone event counts once for each county the zone covers",
            "census_negative_values": "Census sentinels (negative) stored as null",
            "counties_without_events": "0",
        },
        "columns": COLUMN_DEFINITIONS,
    }


def main() -> int:
    """Build and write the county table."""
    zone_path = download_if_missing(ZONE_MAP_URL, RAW_DIR / ZONE_MAP_NAME)
    zone_map = parse_zone_map(zone_path.read_text(encoding="utf-8"))
    storms = parse_storm_events(load_storm_frame(), zone_map, STORM_YEARS)
    census = parse_census(fetch_census_rows())
    table = build_county_table(storms, census)
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    table.write_parquet(OUTPUT_PARQUET, compression=PARQUET_COMPRESSION)
    OUTPUT_META.write_text(json.dumps(build_meta(table), indent=2) + "\n", encoding="utf-8")
    unmatched = storms.filter(~pl.col("fips").is_in(census["fips"].implode())).height
    print(f"counties={table.height} storm_fips_without_census={unmatched}")
    print(f"parquet_bytes={OUTPUT_PARQUET.stat().st_size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
