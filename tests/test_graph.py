"""Unit and integration tests for the LangGraph county campaign pipeline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from county_campaign_builder.county_data import CountyRecord, load_county_table
from county_campaign_builder.domain import (
    VerticalConfig,
    load_compliance_config,
    load_verticals_config,
)
from county_campaign_builder.graph import (
    CampaignDependencies,
    CountyInputDict,
    _build_human_review_list,
    _fallback_comparison,
    _regenerate_failed_assets,
    create_default_dependencies,
    run_campaign,
    run_county_pipeline,
    run_multi_campaign,
)
from county_campaign_builder.llm import (
    COOK_FIPS,
    DALLAS_FIPS,
    DALLAS_TRAP_HAIL_VALUE,
    PINELLAS_FIPS,
    AdsAndLandingPageOutput,
    AnthropicModelClient,
    ComparisonOutput,
    EmailItem,
    FakeModelClient,
    FollowupOutput,
    LlmError,
    ModelClient,
    QualificationQuestionItem,
    QualificationQuestionsOutput,
    RegeneratedAssetItem,
    RegenerateOutput,
    TriggerInterpretationOutput,
    TriggerItem,
)
from county_campaign_builder.models import (
    AdCopy,
    AdDescription,
    AdHeadline,
    CampaignAssets,
    CampaignInput,
    CountyCampaign,
    LandingPageTop,
    MultiCountyInput,
    NumericFact,
    NumericRange,
    QualificationQuestion,
    UnitEconomics,
)
from county_campaign_builder.prompt import NOAA_SOURCE
from county_campaign_builder.settings import Settings


class _StubModelClient:
    """Configurable ModelClient stub built on FakeModelClient for compliance/regen tests."""

    def __init__(
        self,
        *,
        plant_trap: bool = False,
        triggers_override: TriggerInterpretationOutput | None = None,
        questions_override: QualificationQuestionsOutput | None = None,
        ads_lp_override: AdsAndLandingPageOutput | None = None,
        followup_override: FollowupOutput | None = None,
        regen_override: RegenerateOutput | None = None,
        compare_error: bool = False,
    ) -> None:
        self._fake = FakeModelClient(plant_trap=plant_trap)
        self._triggers_override = triggers_override
        self._questions_override = questions_override
        self._ads_lp_override = ads_lp_override
        self._followup_override = followup_override
        self._regen_override = regen_override
        self._compare_error = compare_error
        self.regenerate_calls: list[Sequence[tuple[str, str]]] = []

    def interpret_triggers(
        self,
        county: CountyRecord,
        vertical_config: VerticalConfig,
    ) -> TriggerInterpretationOutput:
        if self._triggers_override is not None:
            return self._triggers_override
        return self._fake.interpret_triggers(county, vertical_config)

    def draft_qualification(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> QualificationQuestionsOutput:
        if self._questions_override is not None:
            return self._questions_override
        return self._fake.draft_qualification(county_name, vertical_config, verified_facts)

    def draft_ads_and_lp(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> AdsAndLandingPageOutput:
        if self._ads_lp_override is not None:
            return self._ads_lp_override
        return self._fake.draft_ads_and_lp(county_name, vertical_config, verified_facts)

    def draft_followup(
        self,
        county_name: str,
        brand_name: str,
        verified_facts: Sequence[NumericFact],
    ) -> FollowupOutput:
        if self._followup_override is not None:
            return self._followup_override
        return self._fake.draft_followup(county_name, brand_name, verified_facts)

    def regenerate_assets(
        self,
        county_name: str,
        brand_name: str,
        failed_items: Sequence[tuple[str, str]],
        vertical_config: VerticalConfig,
    ) -> RegenerateOutput:
        self.regenerate_calls.append(list(failed_items))
        if self._regen_override is not None:
            return self._regen_override
        return self._fake.regenerate_assets(county_name, brand_name, failed_items, vertical_config)

    def compare_counties(self, campaign_summaries: Sequence[str]) -> ComparisonOutput:
        if self._compare_error:
            raise LlmError("Simulated comparison failure.")
        return self._fake.compare_counties(campaign_summaries)


def _deps_with_model(model: ModelClient) -> CampaignDependencies:
    project_root = Path(__file__).resolve().parents[1]
    return CampaignDependencies(
        model=model,
        county_table=load_county_table(project_root / "data" / "counties.parquet"),
        compliance_config=load_compliance_config(project_root / "config" / "compliance.json"),
        verticals_config=load_verticals_config(project_root / "config" / "verticals.json"),
    )


def test_create_default_dependencies_fake_live_and_custom_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FAKE_MODEL", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_ACCESS_CODE", raising=False)

    default_deps = create_default_dependencies()
    assert isinstance(default_deps.model, FakeModelClient)
    assert DALLAS_FIPS in default_deps.county_table

    fake_settings = Settings(fake_model=True)
    fake_deps = create_default_dependencies(settings=fake_settings)
    assert isinstance(fake_deps.model, FakeModelClient)

    live_settings = Settings(
        fake_model=False,
        anthropic_api_key=SecretStr("sk-ant-test-key"),
        live_access_code=SecretStr("access-code"),
    )
    live_deps = create_default_dependencies(settings=live_settings)
    assert isinstance(live_deps.model, AnthropicModelClient)

    project_root = Path(__file__).resolve().parents[1]
    custom_compliance = tmp_path / "compliance.json"
    compliance_data = json.loads(
        (project_root / "config" / "compliance.json").read_text(encoding="utf-8")
    )
    compliance_data["version"] = "custom-compliance"
    custom_compliance.write_text(json.dumps(compliance_data), encoding="utf-8")

    custom_verticals = tmp_path / "verticals.json"
    verticals_data = json.loads(
        (project_root / "config" / "verticals.json").read_text(encoding="utf-8")
    )
    verticals_data["version"] = "custom-verticals"
    custom_verticals.write_text(json.dumps(verticals_data), encoding="utf-8")

    custom_deps = create_default_dependencies(
        settings=fake_settings,
        table_path=project_root / "data" / "counties.parquet",
        compliance_path=custom_compliance,
        verticals_path=custom_verticals,
    )
    assert custom_deps.compliance_config.version == "custom-compliance"
    assert custom_deps.verticals_config.version == "custom-verticals"


def test_run_campaign_dallas_catches_planted_trap_and_computes_economics() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))
    campaign = run_campaign(
        CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        deps,
    )

    assert campaign.status == "success"
    assert campaign.county_fips == DALLAS_FIPS
    assert campaign.county_name == "Dallas County, Texas"

    # Dallas planted trap (120 against authoritative 102) must be caught and corrected.
    assert len(campaign.corrections) == 1
    correction = campaign.corrections[0]
    assert correction.field == "hail_reports_1in"
    assert correction.llm_value == DALLAS_TRAP_HAIL_VALUE
    assert correction.source_value == 102

    hail_fact = next(f for f in campaign.facts if f.field == "hail_reports_1in")
    assert hail_fact.status == "corrected"
    assert hail_fact.value == 102
    assert all(f.status in {"verified", "corrected"} for f in campaign.facts)

    assert campaign.unit_economics.verdict == "green"
    assert campaign.unit_economics.cpl_best_usd == 30.0
    assert campaign.unit_economics.cpl_worst_usd == 83.33
    assert campaign.unit_economics.max_cpc_usd == 7.2

    assert len(campaign.assets.questions) == 5
    assert all(q.status == "approved" for q in campaign.assets.questions)
    assert len(campaign.assets.ad_copy.headlines) == 3
    assert all(h.status == "approved" for h in campaign.assets.ad_copy.headlines)
    assert len(campaign.assets.ad_copy.descriptions) == 2
    assert all(d.status == "approved" for d in campaign.assets.ad_copy.descriptions)
    assert campaign.assets.landing_page is not None
    assert campaign.assets.landing_page.status == "approved"
    assert len(campaign.assets.sms_messages) == 2
    assert all(s.status == "approved" for s in campaign.assets.sms_messages)
    assert len(campaign.assets.email_followups) == 2
    assert all(e.status == "approved" for e in campaign.assets.email_followups)
    assert campaign.needs_human_review == []


def test_run_campaign_canonical_traffic_lights_pinellas_and_cook() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))

    pinellas = run_campaign(
        CampaignInput(
            county_fips=PINELLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=85.0,
            cpc_usd=NumericRange(min=4.0, max=7.0),
            landing_cvr=NumericRange(min=0.05, max=0.09),
        ),
        deps,
    )
    assert pinellas.status == "success"
    assert pinellas.unit_economics.verdict == "yellow"

    cook = run_campaign(
        CampaignInput(
            county_fips=COOK_FIPS,
            vertical="roofing",
            bid_per_lead_usd=60.0,
            cpc_usd=NumericRange(min=6.0, max=9.0),
            landing_cvr=NumericRange(min=0.04, max=0.07),
        ),
        deps,
    )
    assert cook.status == "success"
    assert cook.unit_economics.verdict == "red"


def test_run_campaign_error_paths_invalid_fips_unknown_vertical_and_llm_error() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))

    missing_fips = run_campaign(
        CampaignInput(
            county_fips="99999",
            vertical="motivated_seller",
            bid_per_lead_usd=100.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        ),
        deps,
    )
    assert missing_fips.status == "failed"
    assert missing_fips.error_message == "FIPS not found in county table"


def test_run_county_pipeline_unknown_vertical_and_economics_failure() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))
    empty_verticals = deps.verticals_config.model_copy(update={"verticals": {}})
    deps_no_verticals = CampaignDependencies(
        model=deps.model,
        county_table=deps.county_table,
        compliance_config=deps.compliance_config,
        verticals_config=empty_verticals,
    )
    county_input: CountyInputDict = {
        "fips": DALLAS_FIPS,
        "vertical": "motivated_seller",
        "bid_per_lead_usd": 100.0,
        "cpc_usd": NumericRange(min=3.0, max=5.0),
        "landing_cvr": NumericRange(min=0.05, max=0.10),
    }
    missing_vertical = run_county_pipeline(county_input, deps_no_verticals)
    assert missing_vertical.status == "failed"
    assert missing_vertical.error_message == "Unknown vertical: motivated_seller"

    zero_cvr_input: CountyInputDict = {
        "fips": DALLAS_FIPS,
        "vertical": "motivated_seller",
        "bid_per_lead_usd": 100.0,
        "cpc_usd": NumericRange(min=3.0, max=5.0),
        "landing_cvr": NumericRange(min=0.0, max=0.0),
    }
    econ_failed = run_county_pipeline(zero_cvr_input, deps)
    assert econ_failed.status == "failed"
    assert econ_failed.unit_economics.verdict == "red"
    assert "Unit economics unavailable:" in econ_failed.unit_economics.explanation

    error_deps = _deps_with_model(FakeModelClient(simulate_error=True))
    llm_failed = run_campaign(
        CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        error_deps,
    )
    assert llm_failed.status == "failed"
    assert llm_failed.error_message is not None
    assert "Simulated LLM client failure" in llm_failed.error_message
    assert llm_failed.unit_economics.verdict == "green"


def test_run_campaign_regeneration_compliant_and_still_rejected_branches() -> None:
    bad_ads_lp = AdsAndLandingPageOutput(
        headlines=[
            "This headline is definitely way longer than thirty characters",
            "Adults only home offer",
            "Valid Short Headline",
        ],
        descriptions=[
            (
                "This description intentionally exceeds the ninety character limit "
                "by a wide margin for testing."
            ),
            "Valid short description for local homeowners.",
        ],
        lp_headline="Adults only Dallas homes",
        lp_subheadline="Work directly with Example Home Buyers.",
        cta_text="Get Offer",
        bullet_points=["No hidden steps", "Direct team"],
        consent_disclosure="We may call you.",
    )
    bad_followup = FollowupOutput(
        sms_messages=[
            "Missing brand and opt out text",
            "Example Home Buyers: Valid SMS follow up. Reply STOP to opt out.",
        ],
        emails=[
            EmailItem(
                subject="Adults only neighborhood offer",
                body="Neighborhood is changing fast.",
            ),
            EmailItem(
                subject="Checking in from Example Home Buyers",
                body="Reply anytime to discuss your property.",
            ),
        ],
    )

    # Case 1: Regenerated assets are compliant -> marked "regenerated".
    compliant_regen = RegenerateOutput(
        assets=[
            RegeneratedAssetItem(item_id="headline_1", text="Sell Dallas Home As-Is"),
            RegeneratedAssetItem(item_id="headline_2", text="Fair Cash Home Offer"),
            RegeneratedAssetItem(
                item_id="description_1",
                text="Request a straightforward cash offer for your Dallas home.",
            ),
            RegeneratedAssetItem(
                item_id="lp_headline",
                text="Request a Cash Offer in Dallas County",
            ),
            RegeneratedAssetItem(
                item_id="lp_consent_disclosure",
                text=(
                    "Agree to automated calls and texts. Consent is not a condition of purchase. "
                    "Reply STOP to opt out."
                ),
            ),
            RegeneratedAssetItem(
                item_id="sms_1",
                text="Example Home Buyers: Following up on your request. Reply STOP to opt out.",
            ),
            RegeneratedAssetItem(item_id="email_1_subject", text="Your Dallas property inquiry"),
            RegeneratedAssetItem(
                item_id="email_1_body",
                text="Thank you for contacting Example Home Buyers about your home.",
            ),
        ]
    )
    stub_compliant = _StubModelClient(
        ads_lp_override=bad_ads_lp,
        followup_override=bad_followup,
        regen_override=compliant_regen,
    )
    campaign_ok = run_campaign(
        CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        _deps_with_model(stub_compliant),
    )

    assert len(stub_compliant.regenerate_calls) == 1
    assert campaign_ok.status == "success"
    assert [h.status for h in campaign_ok.assets.ad_copy.headlines] == [
        "regenerated",
        "regenerated",
        "approved",
    ]
    assert [d.status for d in campaign_ok.assets.ad_copy.descriptions] == [
        "regenerated",
        "approved",
    ]
    assert campaign_ok.assets.landing_page is not None
    assert campaign_ok.assets.landing_page.status == "regenerated"
    assert [s.status for s in campaign_ok.assets.sms_messages] == ["regenerated", "approved"]
    assert [e.status for e in campaign_ok.assets.email_followups] == ["regenerated", "approved"]
    assert campaign_ok.needs_human_review == []

    # Case 2: Regenerated assets are still non-compliant -> marked "rejected" and sent to review.
    still_bad_regen = RegenerateOutput(
        assets=[
            RegeneratedAssetItem(
                item_id="headline_1",
                text="Still way over thirty characters for a Google ad headline",
            ),
            RegeneratedAssetItem(
                item_id="description_1",
                text=(
                    "Still way over ninety characters for a Google search ad description "
                    "because it keeps going and going."
                ),
            ),
            RegeneratedAssetItem(item_id="lp_consent_disclosure", text="Still missing phrases."),
            RegeneratedAssetItem(
                item_id="sms_1",
                text="Example Home Buyers: still missing keyword.",
            ),
            RegeneratedAssetItem(item_id="email_1_subject", text="Adults only special"),
        ]
    )
    stub_rejected = _StubModelClient(
        ads_lp_override=bad_ads_lp,
        followup_override=bad_followup,
        regen_override=still_bad_regen,
    )
    campaign_rejected = run_campaign(
        CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        _deps_with_model(stub_rejected),
    )

    assert len(stub_rejected.regenerate_calls) == 1
    assert campaign_rejected.assets.ad_copy.headlines[0].status == "rejected"
    assert campaign_rejected.assets.ad_copy.headlines[1].status == "rejected"
    assert campaign_rejected.assets.ad_copy.descriptions[0].status == "rejected"
    assert campaign_rejected.assets.landing_page is not None
    assert campaign_rejected.assets.landing_page.status == "rejected"
    assert campaign_rejected.assets.sms_messages[0].status == "rejected"
    assert campaign_rejected.assets.email_followups[0].status == "rejected"

    review_items = {item.item: item for item in campaign_rejected.needs_human_review}
    assert review_items["headline_1"].rule_id == "asset-rejected"
    assert review_items["description_1"].rule_id == "asset-rejected"
    assert review_items["landing_page"].rule_id == "asset-rejected"
    assert review_items["sms_1"].rule_id == "asset-rejected"
    assert review_items["email_1"].rule_id == "asset-rejected"


def test_run_campaign_human_review_triggers_missing_topics_and_unverified_facts() -> None:
    triggers = TriggerInterpretationOutput(
        triggers=[
            TriggerItem(
                claim="999 made up county metric",
                field="nonexistent_field",
                value=999,
                source=NOAA_SOURCE,
            )
        ]
    )
    # Only 1 topic covered -> 4 missing topics flagged.
    questions = QualificationQuestionsOutput(
        questions=[QualificationQuestionItem(question="How soon are you looking to sell?")]
    )
    ads_lp = AdsAndLandingPageOutput(
        headlines=[
            "Close in 7 days for cash",
            "Cash offer in 24 hours",
            "Sell Dallas Home As-Is",
        ],
        descriptions=[
            "Guaranteed offer with no fees for your Dallas property.",
            "Get a free roof inspection and top dollar quote today.",
        ],
        lp_headline="Close in 7 days with a cash offer in 24 hours",
        lp_subheadline="Guaranteed timeline with no closing costs.",
        cta_text="Get Offer",
        bullet_points=["No commissions"],
        consent_disclosure=(
            "Agree to automated calls and texts. Consent is not a condition of purchase. "
            "Reply STOP to opt out."
        ),
    )
    followup = FollowupOutput(
        sms_messages=[
            "Example Home Buyers: Close in 7 days with a cash offer in 24 hours. Reply STOP.",
            "Example Home Buyers: Following up on your home. Reply STOP to opt out.",
        ],
        emails=[
            EmailItem(subject="Close in 7 days", body="We guarantee a cash offer in 24 hours."),
            EmailItem(subject="Follow up", body="Reply when ready."),
        ],
    )
    stub = _StubModelClient(
        triggers_override=triggers,
        questions_override=questions,
        ads_lp_override=ads_lp,
        followup_override=followup,
    )
    campaign = run_campaign(
        CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        _deps_with_model(stub),
    )

    assert campaign.status == "success"
    rule_ids = {item.rule_id for item in campaign.needs_human_review}
    item_names = {item.item for item in campaign.needs_human_review}
    assert "review-offer-terms" in rule_ids
    assert "review-insurance-claims" in rule_ids
    assert "unverified-numeric-fact" in rule_ids
    assert "missing-qualification-topic" in rule_ids
    assert "headline_1" in item_names
    assert "headline_2" in item_names
    assert "fact:nonexistent_field" in item_names
    assert "qualification_topic:property_condition" in item_names


def test_regeneration_and_human_review_helpers_edge_branches() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))
    vertical_config = deps.verticals_config.verticals["motivated_seller"]

    ad_copy = AdCopy(
        headlines=[AdHeadline(text="Short", status="approved")],
        descriptions=[AdDescription(text="Short desc", status="approved")],
    )
    unmodified = _regenerate_failed_assets(
        county_name="Dallas County, Texas",
        vertical_config=vertical_config,
        ad_copy=ad_copy,
        landing_page=_build_approved_lp(vertical_config.brand_name),
        sms_messages=[],
        email_followups=[],
        failed_items=[],
        deps=deps,
    )
    assert unmodified[0] == ad_copy

    missing_assets = CampaignAssets(
        questions=[],
        ad_copy=AdCopy(headlines=[], descriptions=[]),
        landing_page=None,
        sms_messages=[],
        email_followups=[],
    )
    missing_review = _build_human_review_list(
        facts=[],
        assets=missing_assets,
        missing_topics=[],
        compliance=deps.compliance_config,
    )
    missing_items = {item.item: item.rule_id for item in missing_review}
    assert missing_items == {
        "landing_page": "asset-missing",
        "questions": "asset-missing",
        "ad_headlines": "asset-missing",
        "ad_descriptions": "asset-missing",
        "sms_messages": "asset-missing",
        "email_followups": "asset-missing",
    }

    rejected_question_assets = CampaignAssets(
        questions=[
            QualificationQuestion(
                question_index=1,
                question="Invalid question",
                status="rejected",
                rejection_reason="Rejected manually",
            )
        ],
        ad_copy=ad_copy,
        landing_page=_build_approved_lp(vertical_config.brand_name),
    )
    q_review = _build_human_review_list(
        facts=[],
        assets=rejected_question_assets,
        missing_topics=[],
        compliance=deps.compliance_config,
    )
    assert any(item.item == "question_1" and item.rule_id == "asset-rejected" for item in q_review)


def _build_approved_lp(brand_name: str) -> LandingPageTop:
    return LandingPageTop(
        headline="Sell Your Dallas Home",
        subheadline=f"Work with {brand_name}.",
        cta_text="Get Review",
        bullet_points=["Clear steps"],
        consent_disclosure=(
            "Automated texts/calls allowed. Consent is not a condition. Reply STOP to opt out."
        ),
        status="approved",
    )


def test_run_multi_campaign_canonical_three_counties() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))
    comparison = run_multi_campaign(
        MultiCountyInput(
            county_fips_list=[DALLAS_FIPS, PINELLAS_FIPS, COOK_FIPS],
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        deps,
    )

    assert [c.county_fips for c in comparison.campaigns] == [
        DALLAS_FIPS,
        PINELLAS_FIPS,
        COOK_FIPS,
    ]
    assert all(c.status == "success" for c in comparison.campaigns)
    assert comparison.recommended_county_fips == DALLAS_FIPS
    assert "Dallas County, TX (FIPS 48113)" in comparison.summary
    assert "Pinellas County (12103)" in comparison.summary
    assert "Cook County, IL (FIPS 17031)" in comparison.summary


def test_run_multi_campaign_partial_failure_degrades_gracefully() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))
    comparison = run_multi_campaign(
        MultiCountyInput(
            county_fips_list=[DALLAS_FIPS, "99999"],
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        deps,
    )

    assert [c.county_fips for c in comparison.campaigns] == [DALLAS_FIPS, "99999"]
    assert comparison.campaigns[0].status == "success"
    assert comparison.campaigns[1].status == "failed"
    assert comparison.campaigns[1].error_message == "FIPS not found in county table"
    assert comparison.recommended_county_fips == DALLAS_FIPS


def test_run_multi_campaign_all_fail_and_comparison_llm_error_fallbacks() -> None:
    deps = create_default_dependencies(Settings(fake_model=True))

    all_failed = run_multi_campaign(
        MultiCountyInput(
            county_fips_list=["99999", "99998"],
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        deps,
    )
    assert len(all_failed.campaigns) == 2
    assert all(c.status == "failed" for c in all_failed.campaigns)
    assert all_failed.recommended_county_fips is None
    assert "All county pipelines failed" in all_failed.summary

    comp_error_deps = _deps_with_model(_StubModelClient(compare_error=True))
    fallback = run_multi_campaign(
        MultiCountyInput(
            county_fips_list=[DALLAS_FIPS, PINELLAS_FIPS],
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        comp_error_deps,
    )
    assert fallback.recommended_county_fips == DALLAS_FIPS
    assert "LLM comparison unavailable" in fallback.summary

    # Verify _fallback_comparison priority: green beats yellow beats red.
    mixed = [
        CountyCampaign(
            county_fips=COOK_FIPS,
            county_name="Cook County, Illinois",
            vertical="motivated_seller",
            status="success",
            unit_economics=UnitEconomics(
                bid_per_lead_usd=60.0,
                cpl_best_usd=85.71,
                cpl_worst_usd=225.0,
                max_cpc_usd=2.4,
                verdict="red",
                explanation="Red",
            ),
        ),
        CountyCampaign(
            county_fips=PINELLAS_FIPS,
            county_name="Pinellas County, Florida",
            vertical="motivated_seller",
            status="success",
            unit_economics=UnitEconomics(
                bid_per_lead_usd=85.0,
                cpl_best_usd=44.44,
                cpl_worst_usd=140.0,
                max_cpc_usd=4.25,
                verdict="yellow",
                explanation="Yellow",
            ),
        ),
        CountyCampaign(
            county_fips=DALLAS_FIPS,
            county_name="Dallas County, Texas",
            vertical="motivated_seller",
            status="success",
            unit_economics=UnitEconomics(
                bid_per_lead_usd=120.0,
                cpl_best_usd=30.0,
                cpl_worst_usd=83.33,
                max_cpc_usd=7.2,
                verdict="green",
                explanation="Green",
            ),
        ),
    ]
    ranked = _fallback_comparison(mixed, "Deterministic fallback")
    assert ranked.recommended_county_fips == DALLAS_FIPS


def test_run_multi_campaign_missing_comparison_in_state_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = create_default_dependencies(Settings(fake_model=True))

    class _FakeCompiledGraph:
        def invoke(self, initial_state: dict[str, Any]) -> dict[str, Any]:
            _ = initial_state
            return {"campaigns": [], "comparison": None}

    monkeypatch.setattr(
        "county_campaign_builder.graph.compile_campaign_graph",
        lambda _deps: _FakeCompiledGraph(),
    )
    result = run_multi_campaign(
        MultiCountyInput(
            county_fips_list=[DALLAS_FIPS],
            vertical="motivated_seller",
            bid_per_lead_usd=120.0,
            cpc_usd=NumericRange(min=3.0, max=5.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
        deps,
    )
    assert result.recommended_county_fips is None
    assert result.summary == "Comparison was not produced by the campaign graph."
