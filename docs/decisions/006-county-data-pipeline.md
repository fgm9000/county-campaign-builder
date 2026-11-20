# ADR 006 — County Data Pipeline

> 🇺🇸 EN | 🇧🇷 [PT-BR](006-county-data-pipeline.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
Local facts come from structured public data (PRD, Section 7), and live mode must work for any county.

Source check (2026-11-19):
- **NOAA Storm Events:** public annual CSV files (`StormEvents_details-ftp_v1.0_d<YEAR>_c<DATE>.csv.gz`), no key required. Coverage from 1950 through Oct/2025 on the download page. County and hail-size columns are verified against the directory's format PDF in Phase 1.
- **Census ACS 5-year (2020–2024):** API at `/data/2024/acs/acs5`. **Every query requires a key** (free, requested via email). Candidate tables: B25035 (median year built), B25003 (tenure), B25002 (vacancy), and B25077 (median value); county-level availability is verified in Phase 1.

## Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **A — Precomputed table of all counties** | Live mode works for any county; no data API in production | Data has a cutoff date; requires an ETL |
| B — Only the 3 counties | Faster | Live mode is restricted |
| C — Live APIs on demand | Always up to date | Census key in production; large NOAA CSV on every call |

## Decision
Option A:
- `scripts/build_county_table.py` (Polars) downloads the NOAA years, filters county events (hail ≥ 1 inch, high wind, hurricane, and tropical storm), aggregates by FIPS across the last 5 complete years, and joins with ACS;
- output is `data/counties.parquet` (and a `.json` copy for the fake model, if needed), with columns, cutoff date, and source for each field;
- the Census key is used only by the script, read from an environment variable, never in the repository or in production;
- runtime only reads the table.

## Deviations from Standard
The Master Standard does not prescribe an ETL. Adds a script with tests for the aggregation logic (on small versioned samples) and the versioned generated table.

## Consequences
- Positive: data-engineering evidence (Polars); the numeric verifier has a fixed, auditable source.
- Negative: data ages; README states the cutoff date.
- Plan impact: Phase 2.

## Review Criterion
If the file exceeds 5 MB or the ETL requires restricted-license data, reduce columns or years.
