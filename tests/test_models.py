"""Unit tests for Pydantic v2 data contracts in county_campaign_builder.models."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from county_campaign_builder.models import (
    MAX_COUNTIES_PER_COMPARISON,
    AdCopy,
    AdDescription,
    AdHeadline,
    CampaignAssets,
    CampaignComparison,
    CampaignInput,
    CountyCampaign,
    EmailFollowup,
    HumanReviewItem,
    LandingPageTop,
    MultiCountyInput,
    NumericCorrection,
    NumericFact,
    NumericRange,
    QualificationQuestion,
    SMSMessage,
    TrafficLight,
    UnitEconomics,
    Vertical,
    normalize_nfc,
)


def _sample_economics(verdict: TrafficLight = "green") -> UnitEconomics:
    return UnitEconomics(
        bid_per_lead_usd=100.0,
        cpl_best_usd=40.0,
        cpl_worst_usd=80.0,
        max_cpc_usd=5.0,
        verdict=verdict,
        explanation="Profitable across full range.",
    )


def test_normalize_nfc_strips_whitespace_and_composes_unicode() -> None:
    assert normalize_nfc("plain text") == "plain text"
    assert normalize_nfc("  padded text \t\n ") == "padded text"
    decomposed = "  Cafe\u0301  "
    assert normalize_nfc(decomposed) == "Caf\u00e9"


def test_numeric_range_valid_bounds_and_immutability() -> None:
    zero_range = NumericRange(min=0.0, max=0.0)
    assert zero_range.min == 0.0
    assert zero_range.max == 0.0

    valid_range = NumericRange(min=1.5, max=4.25)
    assert valid_range.min == 1.5
    assert valid_range.max == 4.25

    with pytest.raises(ValidationError):
        valid_range.min = 2.0


def test_numeric_range_rejects_inverted_and_negative_bounds() -> None:
    with pytest.raises(ValidationError, match="min must be less than or equal to max"):
        NumericRange(min=5.0, max=4.0)

    with pytest.raises(ValidationError):
        NumericRange(min=-0.1, max=1.0)

    with pytest.raises(ValidationError):
        NumericRange(min=0.0, max=-1.0)


def test_campaign_input_valid_for_both_verticals() -> None:
    seller = CampaignInput(
        county_fips="48113",
        vertical="motivated_seller",
        bid_per_lead_usd=120.0,
        cpc_usd=NumericRange(min=3.0, max=5.0),
        landing_cvr=NumericRange(min=0.05, max=1.0),
    )
    assert seller.county_fips == "48113"
    assert seller.vertical == "motivated_seller"

    roofing = CampaignInput(
        county_fips="12103",
        vertical="roofing",
        bid_per_lead_usd=85.0,
        cpc_usd=NumericRange(min=4.0, max=7.0),
        landing_cvr=NumericRange(min=0.04, max=0.09),
    )
    assert roofing.vertical == "roofing"


@pytest.mark.parametrize("bad_fips", ["4811", "481130", "4811a", "abcde", " 4811", ""])
def test_campaign_input_rejects_invalid_fips(bad_fips: str) -> None:
    with pytest.raises(ValidationError):
        CampaignInput(
            county_fips=bad_fips,
            vertical="motivated_seller",
            bid_per_lead_usd=100.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        )


def test_campaign_input_rejects_invalid_vertical_bid_and_cvr() -> None:
    with pytest.raises(ValidationError):
        CampaignInput(
            county_fips="48113",
            vertical=cast(Vertical, "plumbing"),
            bid_per_lead_usd=100.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        )

    for bad_bid in (0.0, -10.0):
        with pytest.raises(ValidationError):
            CampaignInput(
                county_fips="48113",
                vertical="motivated_seller",
                bid_per_lead_usd=bad_bid,
                cpc_usd=NumericRange(min=2.0, max=4.0),
                landing_cvr=NumericRange(min=0.05, max=0.10),
            )

    with pytest.raises(ValidationError, match="landing_cvr values must be between 0 and 1"):
        CampaignInput(
            county_fips="48113",
            vertical="motivated_seller",
            bid_per_lead_usd=100.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=1.01),
        )

    with pytest.raises(ValidationError, match="min must be less than or equal to max"):
        CampaignInput(
            county_fips="48113",
            vertical="motivated_seller",
            bid_per_lead_usd=100.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.20, max=0.10),
        )


def test_multi_county_input_accepts_one_to_ten_unique_counties() -> None:
    single = MultiCountyInput(
        county_fips_list=["48113"],
        vertical="roofing",
        bid_per_lead_usd=90.0,
        cpc_usd=NumericRange(min=3.0, max=6.0),
        landing_cvr=NumericRange(min=0.05, max=0.12),
    )
    assert len(single.county_fips_list) == 1

    ten_fips = [f"481{idx:02d}" for idx in range(MAX_COUNTIES_PER_COMPARISON)]
    ten = MultiCountyInput(
        county_fips_list=ten_fips,
        vertical="motivated_seller",
        bid_per_lead_usd=90.0,
        cpc_usd=NumericRange(min=3.0, max=6.0),
        landing_cvr=NumericRange(min=0.05, max=0.12),
    )
    assert len(ten.county_fips_list) == 10


def test_multi_county_input_rejects_empty_too_many_and_duplicates() -> None:
    with pytest.raises(ValidationError):
        MultiCountyInput(
            county_fips_list=[],
            vertical="motivated_seller",
            bid_per_lead_usd=90.0,
            cpc_usd=NumericRange(min=3.0, max=6.0),
            landing_cvr=NumericRange(min=0.05, max=0.12),
        )

    eleven_fips = [f"481{idx:02d}" for idx in range(MAX_COUNTIES_PER_COMPARISON + 1)]
    with pytest.raises(ValidationError):
        MultiCountyInput(
            county_fips_list=eleven_fips,
            vertical="motivated_seller",
            bid_per_lead_usd=90.0,
            cpc_usd=NumericRange(min=3.0, max=6.0),
            landing_cvr=NumericRange(min=0.05, max=0.12),
        )

    with pytest.raises(ValidationError, match="must not contain duplicate FIPS codes"):
        MultiCountyInput(
            county_fips_list=["48113", "12103", "48113"],
            vertical="motivated_seller",
            bid_per_lead_usd=90.0,
            cpc_usd=NumericRange(min=3.0, max=6.0),
            landing_cvr=NumericRange(min=0.05, max=0.12),
        )


def test_numeric_fact_and_correction_defaults_and_immutability() -> None:
    fact = NumericFact(
        claim="  Median home value is $295,000  ",
        field=" median_home_value_usd ",
        value=295000,
        source=" Census ACS 2023 ",
    )
    assert fact.claim == "Median home value is $295,000"
    assert fact.field == "median_home_value_usd"
    assert fact.source == "Census ACS 2023"
    assert fact.status == "unverified"

    with pytest.raises(ValidationError):
        fact.status = "verified"

    correction_with_source = NumericCorrection(
        field="owner_occupied_pct",
        llm_value=65.0,
        source_value=62.5,
        reason=" Corrected from 65.0 to 62.5 ",
    )
    assert correction_with_source.source_value == 62.5
    assert correction_with_source.reason == "Corrected from 65.0 to 62.5"

    correction_missing_source = NumericCorrection(
        field="vacancy_pct",
        llm_value=8.1,
        source_value=None,
        reason="Withheld",
    )
    assert correction_missing_source.source_value is None

    with pytest.raises(ValidationError):
        correction_missing_source.llm_value = 9.0


def test_unit_economics_model_creation() -> None:
    econ = UnitEconomics(
        bid_per_lead_usd=85.0,
        cpl_best_usd=44.44,
        cpl_worst_usd=140.0,
        max_cpc_usd=4.25,
        verdict="yellow",
        explanation="  Profitable in favorable conditions.  ",
    )
    assert econ.bid_per_lead_usd == 85.0
    assert econ.cpl_best_usd == 44.44
    assert econ.cpl_worst_usd == 140.0
    assert econ.max_cpc_usd == 4.25
    assert econ.verdict == "yellow"
    assert econ.explanation == "Profitable in favorable conditions."


def test_asset_models_and_campaign_assets_bundle() -> None:
    headline = AdHeadline(text=" Sell Your Dallas House Fast ")
    assert headline.status == "approved"
    assert headline.rejection_reason is None
    assert headline.text == "Sell Your Dallas House Fast"

    rejected_desc = AdDescription(
        text="We buy houses as-is.",
        status="rejected",
        rejection_reason=" Exceeds limit ",
    )
    assert rejected_desc.status == "rejected"
    assert rejected_desc.rejection_reason == "Exceeds limit"

    default_ad_copy = AdCopy()
    assert default_ad_copy.headlines == []
    assert default_ad_copy.descriptions == []

    ad_copy = AdCopy(headlines=[headline], descriptions=[rejected_desc])
    assert len(ad_copy.headlines) == 1
    assert len(ad_copy.descriptions) == 1

    landing_page = LandingPageTop(
        headline=" Get a Fair Cash Offer ",
        subheadline=" Local buyers in Dallas County ",
        cta_text=" Request Offer ",
        bullet_points=[" No repairs ", " Flexible closing "],
        consent_disclosure=" By submitting you agree to automated texts. Reply STOP. ",
    )
    assert landing_page.bullet_points == ["No repairs", "Flexible closing"]
    assert landing_page.status == "approved"

    sms = SMSMessage(
        message_index=1,
        text=" Example Home Buyers: Got your request. Reply STOP to opt out. ",
        char_count=61,
        status="needs_human_review",
    )
    assert sms.message_index == 1
    assert sms.char_count == 61
    assert sms.status == "needs_human_review"

    email = EmailFollowup(
        email_index=1,
        subject=" Your Dallas County Cash Offer ",
        body=" Hi, thanks for reaching out. ",
        status="regenerated",
    )
    assert email.subject == "Your Dallas County Cash Offer"
    assert email.status == "regenerated"

    q_minimal = QualificationQuestion(question_index=1, question=" How soon do you need to sell? ")
    assert q_minimal.topic is None
    assert q_minimal.why is None

    q_full = QualificationQuestion(
        question_index=2,
        question="What repairs are needed?",
        topic="property_condition",
        why="Repairs predict cash-offer fit.",
    )
    assert q_full.topic == "property_condition"
    assert q_full.why == "Repairs predict cash-offer fit."

    empty_bundle = CampaignAssets()
    assert empty_bundle.questions == []
    assert empty_bundle.landing_page is None
    assert empty_bundle.sms_messages == []
    assert empty_bundle.email_followups == []

    full_bundle = CampaignAssets(
        questions=[q_minimal, q_full],
        ad_copy=ad_copy,
        landing_page=landing_page,
        sms_messages=[sms],
        email_followups=[email],
    )
    assert len(full_bundle.questions) == 2
    assert full_bundle.landing_page is landing_page


def test_human_review_county_campaign_and_comparison() -> None:
    review_item = HumanReviewItem(
        item=" Ad Headline 1 ",
        reason=" Unverifiable closing speed claim ",
        rule_id=" review-offer-terms ",
    )
    assert review_item.item == "Ad Headline 1"
    assert review_item.rule_id == "review-offer-terms"

    campaign = CountyCampaign(
        county_fips="48113",
        county_name=" Dallas County, Texas ",
        vertical="motivated_seller",
        unit_economics=_sample_economics("green"),
        needs_human_review=[review_item],
    )
    assert campaign.county_name == "Dallas County, Texas"
    assert campaign.status == "success"
    assert campaign.error_message is None
    assert len(campaign.needs_human_review) == 1

    failed_campaign = CountyCampaign(
        county_fips="99999",
        county_name="Unknown County",
        vertical="roofing",
        status="failed",
        error_message=" County FIPS not found ",
        unit_economics=_sample_economics("red"),
    )
    assert failed_campaign.status == "failed"
    assert failed_campaign.error_message == "County FIPS not found"

    default_comparison = CampaignComparison()
    assert default_comparison.campaigns == []
    assert default_comparison.recommended_county_fips is None
    assert default_comparison.summary == ""

    comparison = CampaignComparison(
        campaigns=[campaign, failed_campaign],
        recommended_county_fips=" 48113 ",
        summary=" Dallas County has the strongest unit economics. ",
    )
    assert len(comparison.campaigns) == 2
    assert comparison.recommended_county_fips == "48113"
    assert comparison.summary == "Dallas County has the strongest unit economics."
