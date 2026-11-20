"""Deterministic DeepEval evaluations over fake-mode campaigns and negative fault injections."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from deepeval.evaluate import assert_test

from county_campaign_builder.graph import (
    CampaignDependencies,
    create_default_dependencies,
    run_campaign,
)
from county_campaign_builder.llm import (
    COOK_FIPS,
    DALLAS_FIPS,
    DALLAS_TRAP_HAIL_VALUE,
    PINELLAS_FIPS,
)
from county_campaign_builder.models import (
    AdCopy,
    AdDescription,
    AdHeadline,
    CampaignAssets,
    CampaignInput,
    CountyCampaign,
    EmailFollowup,
    LandingPageTop,
    NumericCorrection,
    NumericFact,
    NumericRange,
    SMSMessage,
    TrafficLight,
    UnitEconomics,
)
from county_campaign_builder.settings import Settings
from evals.metrics import (
    CharacterLimitMetric,
    ComplianceMetric,
    EconomicsMetric,
    NumericAccuracyMetric,
    QualificationCoverageMetric,
    deterministic_metrics,
    to_test_case,
)


@dataclass(frozen=True)
class CanonicalEvalCase:
    """Single canonical county/vertical scenario for deterministic fake-mode evaluation."""

    case_id: str
    input_data: CampaignInput
    expected_verdict: TrafficLight
    expects_dallas_trap: bool = False


CANONICAL_CASES: tuple[CanonicalEvalCase, ...] = (
    CanonicalEvalCase(
        case_id="dallas_motivated_seller_green",
        input_data=CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        ),
        expected_verdict="green",
        expects_dallas_trap=True,
    ),
    CanonicalEvalCase(
        case_id="pinellas_motivated_seller_yellow",
        input_data=CampaignInput(
            county_fips=PINELLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=4.5, max=9.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        expected_verdict="yellow",
    ),
    CanonicalEvalCase(
        case_id="cook_motivated_seller_red",
        input_data=CampaignInput(
            county_fips=COOK_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            # min CPC 11.0 yields cpl_best=137.50 > 125.0 (10.0 / 0.08 = 125.0 would be yellow).
            cpc_usd=NumericRange(min=11.0, max=15.0),
            landing_cvr=NumericRange(min=0.05, max=0.08),
        ),
        expected_verdict="red",
    ),
    CanonicalEvalCase(
        case_id="dallas_roofing_green",
        input_data=CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="roofing",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        ),
        expected_verdict="green",
        expects_dallas_trap=True,
    ),
)


@pytest.fixture(scope="module")
def deps() -> CampaignDependencies:
    return create_default_dependencies(Settings(fake_model=True))


@pytest.fixture(scope="module")
def dallas_baseline(deps: CampaignDependencies) -> tuple[CampaignInput, CountyCampaign]:
    input_data = CANONICAL_CASES[0].input_data
    return input_data, run_campaign(input_data, deps)


@pytest.mark.parametrize("case", CANONICAL_CASES, ids=lambda case: case.case_id)
def test_canonical_campaigns_pass_all_deterministic_metrics(
    case: CanonicalEvalCase,
    deps: CampaignDependencies,
) -> None:
    campaign = run_campaign(case.input_data, deps)
    assert campaign.status == "success"
    assert campaign.unit_economics.verdict == case.expected_verdict

    if case.expects_dallas_trap:
        hail_corrections = [c for c in campaign.corrections if c.field == "hail_reports_1in"]
        assert len(hail_corrections) == 1
        assert hail_corrections[0].llm_value == DALLAS_TRAP_HAIL_VALUE
        assert hail_corrections[0].source_value == 102

    metrics = deterministic_metrics(case.input_data, deps)
    assert_test(to_test_case(case.input_data, campaign), metrics, run_async=False)
    assert all(metric.is_successful() for metric in metrics)


def test_numeric_accuracy_metric_detects_divergent_and_unrecorded_corrections(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = NumericAccuracyMetric(input_data, deps)

    divergent_fact = NumericFact(
        claim="999 hail reports",
        field="hail_reports_1in",
        value=999,
        source="NOAA Storm Events 2020-2024",
        status="verified",
    )
    bad_verified = campaign.model_copy(update={"facts": [divergent_fact]})
    score = metric.measure(to_test_case(input_data, bad_verified))
    assert score == 0.0
    assert not metric.is_successful()
    assert metric.reason is not None and "!= county record 102" in metric.reason

    corrected_without_record = campaign.model_copy(
        update={
            "facts": [
                NumericFact(
                    claim="102 hail reports",
                    field="hail_reports_1in",
                    value=102,
                    source="NOAA Storm Events 2020-2024",
                    status="corrected",
                )
            ],
            "corrections": [],
        }
    )
    assert metric.measure(to_test_case(input_data, corrected_without_record)) == 0.0
    assert metric.reason is not None and "missing from corrections" in metric.reason

    unknown_county = campaign.model_copy(update={"county_fips": "99999"})
    assert metric.measure(to_test_case(input_data, unknown_county)) == 0.0
    assert metric.reason is not None and "not found in county table" in metric.reason

    non_numeric_fact = campaign.model_copy(
        update={
            "facts": [
                NumericFact(
                    claim="Invalid field",
                    field="nonexistent_field",
                    value=1,
                    source="NOAA",
                    status="verified",
                )
            ]
        }
    )
    assert metric.measure(to_test_case(input_data, non_numeric_fact)) == 0.0
    assert metric.reason is not None and "no numeric value" in metric.reason

    unverified_fact = campaign.model_copy(
        update={
            "facts": [
                NumericFact(
                    claim="Unverified claim",
                    field="nonexistent_field",
                    value=1,
                    source="NOAA",
                    status="unverified",
                )
            ]
        }
    )
    assert metric.measure(to_test_case(input_data, unverified_fact)) == 1.0

    # Verify a_measure delegates cleanly and matches synchronous score on valid baseline.
    async_score = asyncio.run(metric.a_measure(to_test_case(input_data, campaign)))
    assert async_score == 1.0
    assert metric.is_successful()


def test_character_limit_metric_detects_overlong_approved_assets_and_ignores_rejected(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = CharacterLimitMetric(input_data, deps)

    long_headline = AdHeadline(
        text="This approved headline exceeds thirty characters",
        status="approved",
    )
    long_description = AdDescription(
        text="X" * 91,
        status="regenerated",
    )
    long_sms = SMSMessage(
        message_index=1,
        text="Example Home Buyers: " + ("A" * 145) + " STOP",
        char_count=171,
        status="approved",
    )
    bad_assets = campaign.assets.model_copy(
        update={
            "ad_copy": AdCopy(headlines=[long_headline], descriptions=[long_description]),
            "sms_messages": [long_sms],
        }
    )
    bad_campaign = campaign.model_copy(update={"assets": bad_assets})
    assert metric.measure(to_test_case(input_data, bad_campaign)) == 0.0
    assert not metric.is_successful()
    assert metric.reason is not None
    assert "headline_1 exceeds 30 chars" in metric.reason
    assert "description_1 exceeds 90 chars" in metric.reason
    assert "sms_1 exceeds 160 chars" in metric.reason

    rejected_assets = campaign.assets.model_copy(
        update={
            "ad_copy": AdCopy(
                headlines=[long_headline.model_copy(update={"status": "rejected"})],
                descriptions=[long_description.model_copy(update={"status": "rejected"})],
            ),
            "sms_messages": [long_sms.model_copy(update={"status": "rejected"})],
        }
    )
    rejected_campaign = campaign.model_copy(update={"assets": rejected_assets})
    assert metric.measure(to_test_case(input_data, rejected_campaign)) == 1.0
    assert metric.is_successful()


def test_compliance_metric_detects_tcpa_and_fair_housing_violations(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = ComplianceMetric(input_data, deps)

    bad_sms_missing_brand = SMSMessage(
        message_index=1,
        text="Following up on your home. Reply STOP to opt out.",
        char_count=49,
        status="approved",
    )
    bad_sms_missing_stop = SMSMessage(
        message_index=2,
        text="Example Home Buyers: Adults only home inquiry.",
        char_count=46,
        status="approved",
    )
    assert campaign.assets.landing_page is not None
    bad_lp: LandingPageTop = campaign.assets.landing_page.model_copy(
        update={
            "headline": "No kids allowed in this neighborhood",
            "consent_disclosure": "We may contact you by phone.",
        }
    )
    bad_assets: CampaignAssets = campaign.assets.model_copy(
        update={
            "ad_copy": AdCopy(
                headlines=[AdHeadline(text="Adults only cash offer", status="approved")],
                descriptions=[
                    AdDescription(text="Christian neighborhood buyers", status="approved")
                ],
            ),
            "landing_page": bad_lp,
            "sms_messages": [bad_sms_missing_brand, bad_sms_missing_stop],
            "email_followups": [
                EmailFollowup(
                    email_index=1,
                    subject="Neighborhood is changing fast",
                    body="No wheelchairs at showing.",
                    status="approved",
                )
            ],
        }
    )
    bad_campaign = campaign.model_copy(update={"assets": bad_assets})
    assert metric.measure(to_test_case(input_data, bad_campaign)) == 0.0
    assert not metric.is_successful()
    assert metric.reason is not None
    assert "sms_1 missing brand_name" in metric.reason
    assert "sms_2 missing TCPA opt-out keyword" in metric.reason
    assert "consent_disclosure missing TCPA phrase(s)" in metric.reason
    assert "headline_1: fha-familial-status" in metric.reason
    assert "description_1: fha-religion-national-origin-race" in metric.reason
    assert "lp_headline: fha-familial-status" in metric.reason
    assert "email_1_subject: fha-blockbusting" in metric.reason
    assert "email_1_body: fha-disability" in metric.reason


def test_qualification_coverage_metric_detects_missing_topic(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = QualificationCoverageMetric(input_data, deps)

    partial_questions = campaign.assets.questions[:-1]
    bad_campaign = campaign.model_copy(
        update={"assets": campaign.assets.model_copy(update={"questions": partial_questions})}
    )
    assert metric.measure(to_test_case(input_data, bad_campaign)) == 0.0
    assert not metric.is_successful()
    assert metric.reason is not None and "missing qualification topic" in metric.reason


def test_economics_metric_detects_mismatched_numbers_and_verdict(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = EconomicsMetric(input_data, deps)

    wrong_econ = UnitEconomics(
        bid_per_lead_usd=130.0,
        cpl_best_usd=10.0,
        cpl_worst_usd=99.0,
        max_cpc_usd=1.0,
        verdict="red",
        explanation="Manipulated economics",
    )
    bad_campaign = campaign.model_copy(update={"unit_economics": wrong_econ})
    assert metric.measure(to_test_case(input_data, bad_campaign)) == 0.0
    assert not metric.is_successful()
    assert metric.reason is not None
    assert "bid_per_lead_usd mismatch" in metric.reason
    assert "cpl_best_usd mismatch" in metric.reason
    assert "cpl_worst_usd mismatch" in metric.reason
    assert "max_cpc_usd mismatch" in metric.reason
    assert "verdict mismatch" in metric.reason


def test_numeric_correction_dataclass_roundtrip_check(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    metric = NumericAccuracyMetric(input_data, deps)
    wrong_source_correction = campaign.model_copy(
        update={
            "corrections": [
                NumericCorrection(
                    field="hail_reports_1in",
                    llm_value=120,
                    source_value=999,
                    reason="Mismatched source value",
                )
            ]
        }
    )
    assert metric.measure(to_test_case(input_data, wrong_source_correction)) == 0.0
    assert metric.reason is not None and "missing from corrections" in metric.reason


def test_unknown_vertical_guard_in_compliance_and_qualification_metrics(
    deps: CampaignDependencies,
    dallas_baseline: tuple[CampaignInput, CountyCampaign],
) -> None:
    input_data, campaign = dallas_baseline
    empty_verticals = deps.verticals_config.model_copy(update={"verticals": {}})
    deps_no_verticals = CampaignDependencies(
        model=deps.model,
        county_table=deps.county_table,
        compliance_config=deps.compliance_config,
        verticals_config=empty_verticals,
    )
    for metric in (
        ComplianceMetric(input_data, deps_no_verticals),
        QualificationCoverageMetric(input_data, deps_no_verticals),
    ):
        assert metric.measure(to_test_case(input_data, campaign)) == 0.0
        assert metric.reason is not None and "unknown vertical" in metric.reason
