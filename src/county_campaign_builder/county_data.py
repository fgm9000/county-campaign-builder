"""Pure county-table logic: NOAA Storm Events, NWS zone map and Census ACS joined by county FIPS.

No network and no disk access except `load_county_table`; the script does the I/O.
"""

import io
from collections.abc import Sequence
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

STORM_YEARS = range(2020, 2025)
HAIL_MIN_INCHES = 1.0
WIND_MIN_KNOTS = 50.0
HAIL_EVENT_TYPE = "Hail"
WIND_EVENT_TYPE = "Thunderstorm Wind"
TORNADO_EVENT_TYPE = "Tornado"
# Marine variants are excluded: marine zones are not in the NWS land zone-county map.
TROPICAL_EVENT_TYPES = ("Hurricane (Typhoon)", "Tropical Storm", "Tropical Depression")
COUNTY_ROW_TYPE = "C"
ZONE_ROW_TYPE = "Z"
STATE_FIPS_WIDTH = 2
COUNTY_FIPS_WIDTH = 3
ZONE_WIDTH = 3
FIPS_WIDTH = STATE_FIPS_WIDTH + COUNTY_FIPS_WIDTH
PERCENT_DECIMALS = 2
ZONE_MAP_ZONE_COLUMN = "column_1"
ZONE_MAP_COUNTY_FIPS_COLUMN = "column_6"

STORM_COLUMNS = (
    "EVENT_ID",
    "STATE_FIPS",
    "YEAR",
    "CZ_TYPE",
    "CZ_FIPS",
    "CZ_NAME",
    "EVENT_TYPE",
    "MAGNITUDE",
)
COUNT_COLUMNS = ("hail_reports_1in", "severe_wind_reports", "tornado_events", "tropical_events")
KIND_TO_COLUMN = {
    "hail": "hail_reports_1in",
    "wind": "severe_wind_reports",
    "tornado": "tornado_events",
    "tropical": "tropical_events",
}
CENSUS_VARIABLES = {
    "B25035_001E": "median_year_built",
    "B25003_001E": "households",
    "B25003_002E": "owner_occupied",
    "B25002_001E": "housing_units",
    "B25002_003E": "vacant_units",
    "B25077_001E": "median_home_value_usd",
    # Motivated-seller signals: long-tenure owners (more equity) and homes owned free and clear.
    "B25038_002E": "tenure_owner_total",
    "B25038_007E": "owners_moved_in_1990s",
    "B25038_008E": "owners_moved_in_1989_or_earlier",
    "B25081_001E": "mortgage_status_total",
    "B25081_009E": "units_without_mortgage",
}
CENSUS_COLUMNS = (
    "fips",
    "county_name",
    "median_year_built",
    "households",
    "owner_occupied",
    "owner_occupied_pct",
    "housing_units",
    "vacant_units",
    "vacancy_pct",
    "median_home_value_usd",
    "owner_long_tenure_pct",
    "free_and_clear_pct",
)


class CountyRecord(BaseModel):
    """One county row as the runtime reads it; None means the Census withheld the value."""

    model_config = ConfigDict(frozen=True)

    fips: str
    county_name: str
    hail_reports_1in: int
    severe_wind_reports: int
    tornado_events: int
    tropical_events: int
    years_covered: str
    median_year_built: int | None
    households: int | None
    owner_occupied: int | None
    owner_occupied_pct: float | None
    housing_units: int | None
    vacant_units: int | None
    vacancy_pct: float | None
    median_home_value_usd: int | None
    owner_long_tenure_pct: float | None
    free_and_clear_pct: float | None


def years_label(years: range) -> str:
    """Return the covered window as text, for example `2020-2024`."""
    return f"{years[0]}-{years[-1]}"


def read_storm_events(raw: bytes) -> pl.DataFrame:
    """Read one decompressed NOAA details CSV (latin-1) keeping only the columns the ETL uses.

    Everything stays text (the files mix padded and unpadded codes); parsing happens later.
    """
    text = raw.decode("latin-1")
    return pl.read_csv(io.StringIO(text), columns=list(STORM_COLUMNS), infer_schema=False)


def parse_zone_map(text: str) -> pl.DataFrame:
    """Parse the NWS `bp*.dbx` zone-county file into `state_fips`, `zone`, `county_fips`.

    The file has no header and uses `|`. A zone can cover several counties, so a zone appears in
    one row per county. Rows without a 5-digit county FIPS are dropped.
    """
    raw = pl.read_csv(io.StringIO(text), separator="|", has_header=False, infer_schema=False)
    return (
        raw.select(
            pl.col(ZONE_MAP_ZONE_COLUMN).str.strip_chars().str.zfill(ZONE_WIDTH).alias("zone"),
            pl.col(ZONE_MAP_COUNTY_FIPS_COLUMN).str.strip_chars().alias("county_fips"),
        )
        .filter(pl.col("county_fips").str.len_chars() == FIPS_WIDTH)
        .with_columns(pl.col("county_fips").str.slice(0, STATE_FIPS_WIDTH).alias("state_fips"))
        .select("state_fips", "zone", "county_fips")
        .unique()
        .sort("state_fips", "zone", "county_fips")
    )


def _kind_expression() -> pl.Expr:
    event = pl.col("EVENT_TYPE")
    magnitude = pl.col("MAGNITUDE")
    return (
        pl.when((event == HAIL_EVENT_TYPE) & (magnitude >= HAIL_MIN_INCHES))
        .then(pl.lit("hail"))
        .when((event == WIND_EVENT_TYPE) & (magnitude >= WIND_MIN_KNOTS))
        .then(pl.lit("wind"))
        .when(event == TORNADO_EVENT_TYPE)
        .then(pl.lit("tornado"))
        .when(event.is_in(TROPICAL_EVENT_TYPES))
        .then(pl.lit("tropical"))
        .otherwise(None)
    )


def _classified_events(frame: pl.DataFrame, years: range) -> pl.DataFrame:
    """Keep rows inside the year window that count as one of the four kinds."""
    return (
        frame.select(STORM_COLUMNS)
        .with_columns(
            pl.col("YEAR").cast(pl.Int64, strict=False),
            pl.col("MAGNITUDE").cast(pl.Float64, strict=False),
            pl.col("STATE_FIPS").str.strip_chars().str.zfill(STATE_FIPS_WIDTH),
            pl.col("CZ_FIPS").str.strip_chars().str.zfill(COUNTY_FIPS_WIDTH),
        )
        .with_columns(_kind_expression().alias("kind"))
        .filter(pl.col("YEAR").is_in(list(years)), pl.col("kind").is_not_null())
    )


def _events_by_county(events: pl.DataFrame, zone_map: pl.DataFrame) -> pl.DataFrame:
    """Return `EVENT_ID`, `fips`, `kind` rows: county rows as-is, tropical zone rows fanned out.

    A zone can cover several counties; the event then counts for each covered county.
    Hail, wind and tornado rows are counted only when reported for a county (`CZ_TYPE == "C"`).
    """
    direct = events.filter(pl.col("CZ_TYPE") == COUNTY_ROW_TYPE).select(
        "EVENT_ID", (pl.col("STATE_FIPS") + pl.col("CZ_FIPS")).alias("fips"), "kind"
    )
    by_zone = (
        events.filter(pl.col("CZ_TYPE") == ZONE_ROW_TYPE, pl.col("kind") == "tropical")
        .join(zone_map, left_on=["STATE_FIPS", "CZ_FIPS"], right_on=["state_fips", "zone"])
        .select("EVENT_ID", pl.col("county_fips").alias("fips"), "kind")
    )
    return pl.concat([direct, by_zone])


def parse_storm_events(frame: pl.DataFrame, zone_map: pl.DataFrame, years: range) -> pl.DataFrame:
    """Count the four event kinds per county FIPS inside the year window.

    Rows are deduplicated by (`EVENT_ID`, county, kind). The counts are report/event records, not
    distinct storms. Counties without any qualifying record are absent here; `build_county_table`
    fills them with 0.
    """
    rows = _events_by_county(_classified_events(frame, years), zone_map).unique(
        subset=["EVENT_ID", "fips", "kind"]
    )
    counts = [
        (pl.col("kind") == kind).sum().cast(pl.Int64).alias(column)
        for kind, column in KIND_TO_COLUMN.items()
    ]
    return (
        rows.group_by("fips")
        .agg(counts)
        .with_columns(pl.lit(years_label(years)).alias("years_covered"))
        .sort("fips")
    )


def _clean_int(column: str) -> pl.Expr:
    """Parse text as integer; the Census negative sentinels (such as -666666666) become null."""
    value = pl.col(column).cast(pl.Int64, strict=False)
    return pl.when(value >= 0).then(value).otherwise(None)


def _percent(numerator: str, denominator: str) -> pl.Expr:
    share = pl.col(numerator) * 100.0 / pl.col(denominator)
    return (
        pl.when(pl.col(denominator) > 0)
        .then(share.round(PERCENT_DECIMALS))
        .otherwise(None)
        .cast(pl.Float64)
    )


def parse_census(rows: Sequence[Sequence[str | None]]) -> pl.DataFrame:
    """Parse the ACS JSON table (first row is the header) into one row per county.

    Negative Census sentinels become null; percentages are null when the denominator is 0.
    """
    header = [str(name) for name in rows[0]]
    raw = pl.DataFrame(
        [list(row) for row in rows[1:]], schema=dict.fromkeys(header, pl.String), orient="row"
    )
    typed = raw.select(
        (pl.col("state") + pl.col("county")).alias("fips"),
        pl.col("NAME").alias("county_name"),
        *[_clean_int(source).alias(target) for source, target in CENSUS_VARIABLES.items()],
    )
    long_tenure = pl.col("owners_moved_in_1990s") + pl.col("owners_moved_in_1989_or_earlier")
    return (
        typed.with_columns(long_tenure.alias("owners_moved_in_before_2000"))
        .with_columns(
            _percent("owner_occupied", "households").alias("owner_occupied_pct"),
            _percent("vacant_units", "housing_units").alias("vacancy_pct"),
            _percent("owners_moved_in_before_2000", "tenure_owner_total").alias(
                "owner_long_tenure_pct"
            ),
            _percent("units_without_mortgage", "mortgage_status_total").alias("free_and_clear_pct"),
        )
        .select(CENSUS_COLUMNS)
        .sort("fips")
    )


def build_county_table(
    storms: pl.DataFrame, census: pl.DataFrame, years: range = STORM_YEARS
) -> pl.DataFrame:
    """Left-join storm counts onto the Census counties; counties without events get 0.

    The Census is the base: a county that only appears in the storm data (no ACS row) is dropped.
    """
    census_only = [column for column in census.columns if column not in ("fips", "county_name")]
    return (
        census.join(storms, on="fips", how="left")
        .with_columns(
            *[pl.col(column).fill_null(0) for column in COUNT_COLUMNS],
            pl.col("years_covered").fill_null(years_label(years)),
        )
        .select("fips", "county_name", *COUNT_COLUMNS, "years_covered", *census_only)
    )


def load_county_table(path: Path) -> dict[str, CountyRecord]:
    """Read the parquet written by the ETL into records keyed by county FIPS."""
    records = (CountyRecord.model_validate(row) for row in pl.read_parquet(path).to_dicts())
    return {record.fips: record for record in records}
