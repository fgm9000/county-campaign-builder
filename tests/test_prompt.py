"""Unit tests for deterministic prompt builders."""

from __future__ import annotations

from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.domain import QuestionTopic, VerticalConfig, load_verticals_config
from county_campaign_builder.models import NumericFact
from county_campaign_builder.prompt import (
    AD_DESCRIPTION_MAX_CHARS,
    AD_HEADLINE_MAX_CHARS,
    CENSUS_SOURCE,
    NOAA_SOURCE,
    SMS_MAX_CHARS,
    build_ads_and_lp_prompt,
    build_comparison_prompt,
    build_followup_prompt,
    build_qualification_prompt,
    build_regeneration_prompt,
    build_trigger_interpretation_prompt,
)


def _make_county(
    *,
    fips: str = "48113",
    county_name: str = "Dallas County, Texas",
    median_year_built: int | None = 1983,
    vacancy_pct: float | None = 7.72,
    owner_long_tenure_pct: float | None = 26.6,
    free_and_clear_pct: float | None = 42.69,
) -> CountyRecord:
    return CountyRecord(
        fips=fips,
        county_name=county_name,
        hail_reports_1in=102,
        severe_wind_reports=50,
        tornado_events=5,
        tropical_events=0,
        years_covered="2020-2024",
        median_year_built=median_year_built,
        households=982737,
        owner_occupied=498911,
        owner_occupied_pct=50.77,
        housing_units=1064965,
        vacant_units=82228,
        vacancy_pct=vacancy_pct,
        median_home_value_usd=303000,
        owner_long_tenure_pct=owner_long_tenure_pct,
        free_and_clear_pct=free_and_clear_pct,
    )


def _sample_facts() -> list[NumericFact]:
    return [
        NumericFact(
            claim="102 hail reports of 1 inch or larger in 2020-2024",
            field="hail_reports_1in",
            value=102,
            source=NOAA_SOURCE,
            status="verified",
        ),
        NumericFact(
            claim="42.69% of owner-occupied homes are owned free and clear",
            field="free_and_clear_pct",
            value=42.69,
            source=CENSUS_SOURCE,
            status="verified",
        ),
    ]


def test_build_trigger_interpretation_prompt_full_record() -> None:
    county = _make_county()
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]

    prompt = build_trigger_interpretation_prompt(county, motivated_seller)

    assert "Dallas County, Texas (FIPS: 48113, Storm window: 2020-2024)" in prompt
    assert motivated_seller.label in prompt
    assert motivated_seller.goal in prompt
    assert f"- owner_long_tenure_pct: 26.6 [source: {CENSUS_SOURCE}]" in prompt
    assert f"- free_and_clear_pct: 42.69 [source: {CENSUS_SOURCE}]" in prompt
    assert f"- hail_reports_1in: 102 [source: {NOAA_SOURCE}]" in prompt
    assert ": N/A (withheld by source)" not in prompt


def test_build_trigger_interpretation_prompt_withheld_values_and_empty_fields() -> None:
    county = _make_county(
        median_year_built=None,
        vacancy_pct=None,
        owner_long_tenure_pct=None,
    )
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]

    prompt = build_trigger_interpretation_prompt(county, motivated_seller)

    assert f"- owner_long_tenure_pct: N/A (withheld by source) [source: {CENSUS_SOURCE}]" in prompt
    assert f"- vacancy_pct: N/A (withheld by source) [source: {CENSUS_SOURCE}]" in prompt
    assert f"- median_year_built: N/A (withheld by source) [source: {CENSUS_SOURCE}]" in prompt
    assert f"- free_and_clear_pct: 42.69 [source: {CENSUS_SOURCE}]" in prompt
    assert "Do NOT cite any field marked N/A (withheld by source)." in prompt

    empty_fields_vertical = VerticalConfig(
        label="Custom",
        goal="Test empty trigger fields",
        trigger_fields=[],
        required_question_topics=[QuestionTopic(topic="timeline", why="Timing", keywords=["when"])],
        brand_name="Test Brand",
    )
    empty_prompt = build_trigger_interpretation_prompt(county, empty_fields_vertical)
    assert "- None configured." in empty_prompt


def test_build_qualification_prompt_empty_and_verified_facts() -> None:
    verticals = load_verticals_config()
    roofing = verticals.verticals["roofing"]

    prompt_empty = build_qualification_prompt("Dallas County, Texas", roofing, [])
    assert "Target County: Dallas County, Texas" in prompt_empty
    assert f"Brand: {roofing.brand_name}" in prompt_empty
    assert "- None provided. Do not invent or assume any county statistics." in prompt_empty
    for topic in roofing.required_question_topics:
        assert f"Topic: {topic.topic}" in prompt_empty
        assert f"Why this matters: {topic.why}" in prompt_empty

    facts = _sample_facts()
    prompt_with_facts = build_qualification_prompt("Dallas County, Texas", roofing, facts)
    assert facts[0].claim in prompt_with_facts
    assert f"(field: hail_reports_1in, value: 102, source: {NOAA_SOURCE})" in prompt_with_facts
    assert facts[1].claim in prompt_with_facts

    no_topics_vertical = VerticalConfig(
        label="Empty Topics",
        goal="Goal",
        trigger_fields=["hail_reports_1in"],
        required_question_topics=[],
        brand_name="BrandX",
    )
    prompt_no_topics = build_qualification_prompt("Dallas County, Texas", no_topics_vertical, [])
    assert "- No topics configured." in prompt_no_topics


def test_build_ads_and_lp_prompt_limits_tcpa_and_fair_housing() -> None:
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]
    facts = _sample_facts()

    prompt = build_ads_and_lp_prompt("Dallas County, Texas", motivated_seller, facts)

    assert f"Brand Name: {motivated_seller.brand_name}" in prompt
    assert f"STRICT limit <= {AD_HEADLINE_MAX_CHARS} characters" in prompt
    assert f"STRICT limit <= {AD_DESCRIPTION_MAX_CHARS} characters" in prompt
    assert '"automated"' in prompt
    assert '"not a condition"' in prompt
    assert '"stop"' in prompt
    assert "Fair Housing (42 U.S.C. 3604(c) and (e))" in prompt
    assert "NO familial status limits" in prompt
    assert "NO blockbusting language" in prompt
    assert facts[0].claim in prompt

    prompt_no_facts = build_ads_and_lp_prompt("Dallas County, Texas", motivated_seller, [])
    assert "- None provided. Do not invent or assume any county statistics." in prompt_no_facts


def test_build_followup_prompt_brand_sms_limit_and_opt_out() -> None:
    facts = _sample_facts()
    prompt = build_followup_prompt("Dallas County, Texas", "Example Home Buyers", facts)

    assert "Target County: Dallas County, Texas" in prompt
    assert "Brand Name: Example Home Buyers" in prompt
    assert f"STRICT limit: <= {SMS_MAX_CHARS} characters per SMS" in prompt
    assert 'Each SMS MUST include the exact brand name "Example Home Buyers".' in prompt
    assert "Reply STOP to opt out" in prompt
    assert facts[1].claim in prompt


def test_build_regeneration_prompt_empty_and_non_empty_failed_items() -> None:
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]

    empty_prompt = build_regeneration_prompt(
        county_name="Dallas County, Texas",
        brand_name="Example Home Buyers",
        failed_items=[],
        vertical_config=motivated_seller,
    )
    assert "- No failed items provided." in empty_prompt

    failed_items = [
        ("headline_1", "Headline exceeds 30 character limit (38 chars)."),
        ("sms_1", "SMS must include a TCPA opt-out keyword (e.g., STOP)."),
    ]
    non_empty_prompt = build_regeneration_prompt(
        county_name="Dallas County, Texas",
        brand_name="Example Home Buyers",
        failed_items=failed_items,
        vertical_config=motivated_seller,
    )
    assert "1. Item: headline_1" in non_empty_prompt
    assert "Headline exceeds 30 character limit (38 chars)." in non_empty_prompt
    assert "2. Item: sms_1" in non_empty_prompt
    assert "SMS must include a TCPA opt-out keyword (e.g., STOP)." in non_empty_prompt
    assert f"STRICT <= {AD_HEADLINE_MAX_CHARS} characters" in non_empty_prompt
    assert f"STRICT <= {AD_DESCRIPTION_MAX_CHARS} characters" in non_empty_prompt
    assert f"STRICT <= {SMS_MAX_CHARS} characters" in non_empty_prompt


def test_build_comparison_prompt_empty_and_multiple_summaries() -> None:
    empty_prompt = build_comparison_prompt([])
    assert "No county campaign summaries provided." in empty_prompt

    summaries = [
        "County: Dallas County, Texas (FIPS 48113) | verdict=green",
        "County: Pinellas County, Florida (FIPS 12103) | verdict=yellow",
        "County: Cook County, Illinois (FIPS 17031) | verdict=red",
    ]
    multi_prompt = build_comparison_prompt(summaries)
    assert "County Summary 1:\nCounty: Dallas County, Texas (FIPS 48113)" in multi_prompt
    assert "County Summary 2:\nCounty: Pinellas County, Florida (FIPS 12103)" in multi_prompt
    assert "County Summary 3:\nCounty: Cook County, Illinois (FIPS 17031)" in multi_prompt
    assert "Unit Economics (Traffic Light)" in multi_prompt
    assert "Launch Recommendation" in multi_prompt
