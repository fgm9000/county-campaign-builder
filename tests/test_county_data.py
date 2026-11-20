"""County table logic on small hand-written NOAA, NWS and Census samples."""

import json
from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from county_campaign_builder.county_data import (
    STORM_YEARS,
    CountyRecord,
    build_county_table,
    load_county_table,
    parse_census,
    parse_storm_events,
    parse_zone_map,
    read_storm_events,
    years_label,
)

FIXTURES = Path(__file__).parent / "fixtures" / "county_data"
DALLAS = "48113"
PINELLAS = "12103"
COOK = "17031"
MCKINLEY = "35031"
SAN_JUAN = "35045"
RIO_ARRIBA = "35039"


@pytest.fixture
def zone_map() -> pl.DataFrame:
    return parse_zone_map((FIXTURES / "zone_map_sample.dbx").read_text(encoding="utf-8"))


@pytest.fixture
def storms(zone_map: pl.DataFrame) -> pl.DataFrame:
    frame = read_storm_events((FIXTURES / "storm_events_sample.csv").read_bytes())
    return parse_storm_events(frame, zone_map, STORM_YEARS)


@pytest.fixture
def census() -> pl.DataFrame:
    rows = json.loads((FIXTURES / "census_sample.json").read_text(encoding="utf-8"))
    return parse_census(rows)


def _row(frame: pl.DataFrame, fips: str) -> dict[str, object]:
    return frame.filter(pl.col("fips") == fips).to_dicts()[0]


def test_zone_map_keeps_one_row_per_zone_county_and_drops_rows_without_fips(
    zone_map: pl.DataFrame,
) -> None:
    assert zone_map.columns == ["state_fips", "zone", "county_fips"]
    assert zone_map["county_fips"].to_list() == [PINELLAS, MCKINLEY, SAN_JUAN, DALLAS]
    assert zone_map["zone"].to_list() == ["050", "201", "201", "119"]


def test_years_label() -> None:
    assert years_label(STORM_YEARS) == "2020-2024"


def test_storm_events_read_latin1_and_keep_only_used_columns() -> None:
    frame = read_storm_events((FIXTURES / "storm_events_sample.csv").read_bytes())
    assert "BEGIN_DATE_TIME" not in frame.columns
    assert "COOK ÉTÉ" in frame["CZ_NAME"].to_list()


def test_hail_counts_from_one_inch_inside_the_window_and_only_for_counties(
    storms: pl.DataFrame,
) -> None:
    assert _row(storms, DALLAS)["hail_reports_1in"] == 2  # 1.75" and the 1.00" boundary
    assert _row(storms, COOK)["hail_reports_1in"] == 1  # 1.00" counts, the null magnitude does not


def test_wind_counts_from_fifty_knots(storms: pl.DataFrame) -> None:
    assert _row(storms, DALLAS)["severe_wind_reports"] == 2  # 60 and the 50 boundary, not 49
    assert _row(storms, COOK)["severe_wind_reports"] == 1


def test_tornado_counts_without_magnitude(storms: pl.DataFrame) -> None:
    assert _row(storms, DALLAS)["tornado_events"] == 1


def test_tropical_counts_county_rows_and_zone_rows(storms: pl.DataFrame) -> None:
    # Pinellas: hurricane by zone 050, tropical storm, hurricane and depression by county.
    assert _row(storms, PINELLAS)["tropical_events"] == 4


def test_tropical_zone_event_counts_for_every_county_the_zone_covers(
    storms: pl.DataFrame,
) -> None:
    assert _row(storms, MCKINLEY)["tropical_events"] == 1
    assert _row(storms, SAN_JUAN)["tropical_events"] == 1


def test_irrelevant_types_unmapped_zones_and_other_years_are_ignored(
    storms: pl.DataFrame,
) -> None:
    assert set(storms["fips"].to_list()) == {PINELLAS, COOK, MCKINLEY, SAN_JUAN, DALLAS}
    assert _row(storms, DALLAS)["hail_reports_1in"] == 2  # 2019, 2025 and the zone hail are out
    assert set(storms["years_covered"].to_list()) == {"2020-2024"}


def test_duplicate_event_rows_count_once(storms: pl.DataFrame) -> None:
    # EVENT_ID 1 appears twice in the sample; Dallas hail stays 2, not 3.
    assert _row(storms, DALLAS)["hail_reports_1in"] == 2


def test_census_sentinel_becomes_null_and_percentages_are_computed(
    census: pl.DataFrame,
) -> None:
    cook = _row(census, COOK)
    assert cook["median_home_value_usd"] is None
    assert cook["owner_occupied_pct"] == 60.63
    assert cook["vacancy_pct"] == 9.09
    dallas = _row(census, DALLAS)
    assert dallas["median_year_built"] == 1983
    assert dallas["county_name"] == "Dallas County, Texas"


def test_census_percentages_are_null_when_the_denominator_is_zero(census: pl.DataFrame) -> None:
    mckinley = _row(census, MCKINLEY)
    assert mckinley["owner_occupied_pct"] is None
    assert mckinley["vacancy_pct"] is None
    assert mckinley["owner_long_tenure_pct"] is None
    assert mckinley["free_and_clear_pct"] is None


def test_motivated_seller_signals_long_tenure_and_free_and_clear(census: pl.DataFrame) -> None:
    dallas = _row(census, DALLAS)
    assert dallas["owner_long_tenure_pct"] == 18.04
    assert dallas["free_and_clear_pct"] == 30.07
    pinellas = _row(census, PINELLAS)
    assert pinellas["owner_long_tenure_pct"] == 33.57
    assert pinellas["free_and_clear_pct"] == 40.28
    cook = _row(census, COOK)
    assert cook["owner_long_tenure_pct"] == 28.86
    assert cook["free_and_clear_pct"] is None


def test_build_table_gives_zero_to_counties_without_events_and_drops_storm_only_counties(
    storms: pl.DataFrame, census: pl.DataFrame
) -> None:
    table = build_county_table(storms, census)
    assert table.height == census.height
    assert SAN_JUAN not in table["fips"].to_list()  # events but no Census row
    quiet = _row(table, RIO_ARRIBA)
    assert [quiet[c] for c in ("hail_reports_1in", "severe_wind_reports")] == [0, 0]
    assert [quiet[c] for c in ("tornado_events", "tropical_events")] == [0, 0]
    assert quiet["years_covered"] == "2020-2024"
    assert _row(table, DALLAS)["hail_reports_1in"] == 2


def test_load_county_table_reads_frozen_records_keyed_by_fips(
    storms: pl.DataFrame, census: pl.DataFrame, tmp_path: Path
) -> None:
    path = tmp_path / "counties.parquet"
    build_county_table(storms, census).write_parquet(path)
    records = load_county_table(path)
    assert isinstance(records[DALLAS], CountyRecord)
    assert records[PINELLAS].tropical_events == 4
    assert records[COOK].median_home_value_usd is None
    with pytest.raises(ValidationError):
        records[COOK].tropical_events = 9
