"""Unit tests for domain config loading, fact verification, and compliance guardrails."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.domain import (
    ComplianceConfig,
    HumanReviewRule,
    TcpaRule,
    VerticalsConfig,
    check_character_limit,
    detect_human_review_triggers,
    find_fair_housing_violations,
    load_compliance_config,
    load_verticals_config,
    match_qualification_questions,
    validate_consent_disclosure,
    validate_sms,
    verify_numeric_facts,
)
from county_campaign_builder.models import NumericFact


def _make_county_record(
    *,
    vacancy_pct: float | None = 8.42,
    median_year_built: int | None = 1984,
) -> CountyRecord:
    return CountyRecord(
        fips="48113",
        county_name="Dallas County, Texas",
        hail_reports_1in=14,
        severe_wind_reports=22,
        tornado_events=3,
        tropical_events=0,
        years_covered="2020-2024",
        median_year_built=median_year_built,
        households=980000,
        owner_occupied=510000,
        owner_occupied_pct=52.04,
        housing_units=1070000,
        vacant_units=90000,
        vacancy_pct=vacancy_pct,
        median_home_value_usd=295000,
        owner_long_tenure_pct=38.15,
        free_and_clear_pct=31.50,
    )


@pytest.fixture
def compliance_config() -> ComplianceConfig:
    return load_compliance_config()


@pytest.fixture
def verticals_config() -> VerticalsConfig:
    return load_verticals_config()


def test_load_compliance_config_default_and_explicit(tmp_path: Path) -> None:
    default_cfg = load_compliance_config()
    assert default_cfg.character_limits.headline == 30
    assert default_cfg.character_limits.description == 90
    assert default_cfg.character_limits.sms == 160

    custom_path = tmp_path / "compliance.json"
    custom_data = default_cfg.model_dump()
    custom_data["version"] = "custom-1"
    custom_path.write_text(json.dumps(custom_data), encoding="utf-8")

    loaded = load_compliance_config(custom_path)
    assert loaded.version == "custom-1"


def test_load_compliance_config_missing_and_invalid(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_compliance_config(tmp_path / "missing.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_compliance_config(bad_json)

    invalid_schema = tmp_path / "invalid.json"
    invalid_schema.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_compliance_config(invalid_schema)


def test_load_verticals_config_default_and_explicit(tmp_path: Path) -> None:
    default_cfg = load_verticals_config()
    assert "motivated_seller" in default_cfg.verticals
    assert "roofing" in default_cfg.verticals

    custom_path = tmp_path / "verticals.json"
    custom_data = default_cfg.model_dump()
    custom_data["version"] = "custom-2"
    custom_path.write_text(json.dumps(custom_data), encoding="utf-8")

    loaded = load_verticals_config(custom_path)
    assert loaded.version == "custom-2"


def test_load_verticals_config_missing_and_invalid(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_verticals_config(tmp_path / "missing.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("[", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_verticals_config(bad_json)

    invalid_schema = tmp_path / "invalid.json"
    invalid_schema.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_verticals_config(invalid_schema)


def test_check_character_limit_within_and_exceeding() -> None:
    assert check_character_limit("Sell House Fast", 30) == (True, 15)
    assert check_character_limit("x" * 30, 30) == (True, 30)
    assert check_character_limit("x" * 31, 30) == (False, 31)


def test_verify_numeric_facts_all_outcomes() -> None:
    county = _make_county_record(vacancy_pct=None)
    facts = [
        NumericFact(
            claim="14 hail reports",
            field="hail_reports_1in",
            value=14,
            source="NOAA",
        ),
        NumericFact(
            claim="52.04% owner occupied",
            field="owner_occupied_pct",
            value=52.045,
            source="Census ACS",
        ),
        NumericFact(
            claim="25 severe wind reports",
            field="severe_wind_reports",
            value=25,
            source="NOAA",
        ),
        NumericFact(
            claim="40.0% long tenure",
            field="owner_long_tenure_pct",
            value=40.0,
            source="Census ACS",
        ),
        NumericFact(
            claim="Unknown field",
            field="nonexistent_metric",
            value=10,
            source="Guess",
        ),
        NumericFact(
            claim="Withheld vacancy",
            field="vacancy_pct",
            value=7.5,
            source="Census ACS",
        ),
        NumericFact(
            claim="Non-numeric string attribute",
            field="county_name",
            value=1,
            source="Census ACS",
        ),
    ]

    verified, corrections = verify_numeric_facts(facts, county)

    assert [f.status for f in verified] == [
        "verified",
        "verified",
        "corrected",
        "corrected",
        "unverified",
        "unverified",
        "unverified",
    ]
    assert verified[0].value == 14
    assert verified[1].value == 52.045
    assert verified[2].value == 22
    assert verified[3].value == 38.15
    assert verified[4].value == 10
    assert verified[5].value == 7.5
    assert verified[6].value == 1

    assert len(corrections) == 5
    assert corrections[0].field == "severe_wind_reports"
    assert corrections[0].llm_value == 25
    assert corrections[0].source_value == 22
    assert "22" in corrections[0].reason

    assert corrections[1].field == "owner_long_tenure_pct"
    assert corrections[1].llm_value == 40.0
    assert corrections[1].source_value == 38.15

    assert corrections[2].field == "nonexistent_metric"
    assert corrections[2].source_value is None
    assert "not available" in corrections[2].reason

    assert corrections[3].field == "vacancy_pct"
    assert corrections[3].source_value is None

    assert corrections[4].field == "county_name"
    assert corrections[4].source_value is None


def test_find_fair_housing_violations(compliance_config: ComplianceConfig) -> None:
    clean = "Sell your Dallas County home as-is with a flexible closing date."
    assert find_fair_housing_violations(clean, compliance_config) == []

    familial = "Quiet community, adults only, no kids and not suitable for children."
    familial_hits = find_fair_housing_violations(familial, compliance_config)
    assert any(hit.startswith("fha-familial-status:") for hit in familial_hits)

    race_religion = "Christian neighborhood in a white community."
    race_hits = find_fair_housing_violations(race_religion, compliance_config)
    assert any(hit.startswith("fha-religion-national-origin-race:") for hit in race_hits)

    disability = "Must be able-bodied; no wheelchairs allowed."
    disability_hits = find_fair_housing_violations(disability, compliance_config)
    assert any(hit.startswith("fha-disability:") for hit in disability_hits)

    blockbusting = "This neighborhood is changing fast—sell before values drop."
    blockbusting_hits = find_fair_housing_violations(blockbusting, compliance_config)
    assert any(hit.startswith("fha-blockbusting:") for hit in blockbusting_hits)


def test_validate_sms_compliant_and_error_cases(compliance_config: ComplianceConfig) -> None:
    brand = "Example Home Buyers"
    valid = (
        "Hi from Example Home Buyers: we received your Dallas property inquiry. "
        "Reply STOP to opt out."
    )
    assert validate_sms(valid, brand, compliance_config) == []

    # Case-insensitive brand and alternative opt-out keyword
    valid_alt = "example home buyers here with your offer update. Reply UNSUBSCRIBE anytime."
    assert validate_sms(valid_alt, brand, compliance_config) == []

    too_long = f"{brand}: " + ("a" * 150) + " Reply STOP"
    long_errors = validate_sms(too_long, brand, compliance_config)
    assert len(long_errors) == 1
    assert "160 character limit" in long_errors[0]

    missing_brand = "Thanks for reaching out about your home. Reply STOP to opt out."
    brand_errors = validate_sms(missing_brand, brand, compliance_config)
    assert brand_errors == [f"SMS must identify sender brand '{brand}'."]

    # "unstoppable" contains "stop" as substring, not as whole word
    missing_opt_out = f"{brand}: unstoppable service for your home sale."
    opt_out_errors = validate_sms(missing_opt_out, brand, compliance_config)
    assert opt_out_errors == ["SMS must include a TCPA opt-out keyword (e.g., STOP)."]


def test_validate_consent_disclosure(compliance_config: ComplianceConfig) -> None:
    compliant = (
        "By submitting, you agree to receive automated marketing texts and calls. "
        "Consent is not a condition of purchase. Reply STOP to opt out."
    )
    assert validate_consent_disclosure(compliant, compliance_config) == []

    partial = "You agree to receive automated messages."
    missing = validate_consent_disclosure(partial, compliance_config)
    assert missing == ["not a condition", "stop"]

    # Duplicate required phrase across rules should only be reported once
    dup_rule = TcpaRule(
        rule_id="dup-consent",
        reference="47 CFR 64.1200",
        description="Duplicate phrase check",
        required_phrases=["stop", "written consent"],
    )
    custom_tcpa = compliance_config.tcpa_sms.model_copy(
        update={"rules": [*compliance_config.tcpa_sms.rules, dup_rule]}
    )
    custom_cfg = compliance_config.model_copy(update={"tcpa_sms": custom_tcpa})
    assert validate_consent_disclosure("none", custom_cfg) == [
        "automated",
        "not a condition",
        "stop",
        "written consent",
    ]


def test_detect_human_review_triggers_and_deduplication(
    compliance_config: ComplianceConfig,
) -> None:
    clean = "Request a local property evaluation for your Dallas home."
    assert detect_human_review_triggers(clean, "Headline 1", compliance_config) == []

    offer_text = "Guaranteed cash offer, close in 7 days with no fees."
    offer_items = detect_human_review_triggers(offer_text, "Ad Copy 1", compliance_config)
    assert len(offer_items) == 1
    assert offer_items[0].item == "Ad Copy 1"
    assert offer_items[0].rule_id == "review-offer-terms"

    insurance_text = "Insurance will cover everything so you get a free roof."
    insurance_items = detect_human_review_triggers(
        insurance_text, "Landing Page", compliance_config
    )
    assert len(insurance_items) == 1
    assert insurance_items[0].rule_id == "review-insurance-claims"

    # Explicit duplicate rule_id entries in config are also deduplicated
    dup_rule = HumanReviewRule(
        rule_id="review-offer-terms",
        reason="Duplicate rule id",
        patterns=[r"\bcash buyer\b"],
    )
    custom_patterns = compliance_config.human_review_patterns.model_copy(
        update={"rules": [*compliance_config.human_review_patterns.rules, dup_rule]}
    )
    custom_cfg = compliance_config.model_copy(update={"human_review_patterns": custom_patterns})
    combined = "Guaranteed cash offer from a cash buyer with a free roof."
    combined_items = detect_human_review_triggers(combined, "SMS 1", custom_cfg)
    assert [item.rule_id for item in combined_items] == [
        "review-offer-terms",
        "review-insurance-claims",
    ]


def test_match_qualification_questions_all_topics_partial_and_unmatched(
    verticals_config: VerticalsConfig,
) -> None:
    seller_cfg = verticals_config.verticals["motivated_seller"]

    all_questions = [
        "How soon are you looking to sell?",
        "What is the overall condition and what repairs are needed?",
        "Is the home currently listed with an agent?",
        "Are you the sole owner on the title?",
        "Why are you considering selling right now?",
    ]
    matched, missing = match_qualification_questions(all_questions, seller_cfg)
    assert missing == []
    assert [q.question_index for q in matched] == [1, 2, 3, 4, 5]
    assert [q.topic for q in matched] == [
        "timeline",
        "property_condition",
        "listed_with_agent",
        "decision_maker",
        "reason_for_selling",
    ]
    assert all(q.why is not None and q.status == "approved" for q in matched)

    partial_questions = [
        "What is your ideal timeline to sell?",
        "What is your favorite color?",
    ]
    partial_matched, partial_missing = match_qualification_questions(partial_questions, seller_cfg)
    assert partial_matched[0].topic == "timeline"
    assert partial_matched[1].topic is None
    assert partial_matched[1].why is None
    assert partial_missing == [
        "property_condition",
        "listed_with_agent",
        "decision_maker",
        "reason_for_selling",
    ]
