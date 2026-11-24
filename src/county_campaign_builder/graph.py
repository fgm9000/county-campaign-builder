"""LangGraph county campaign pipeline and multi-county fan-out orchestration."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from county_campaign_builder.county_data import CountyRecord, load_county_table
from county_campaign_builder.domain import (
    ComplianceConfig,
    VerticalConfig,
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
from county_campaign_builder.economics import calculate_unit_economics
from county_campaign_builder.llm import (
    AnthropicModelClient,
    FakeModelClient,
    LlmError,
    ModelClient,
)
from county_campaign_builder.models import (
    AdCopy,
    AdDescription,
    AdHeadline,
    AssetStatus,
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
from county_campaign_builder.settings import Settings

_VERDICT_PRIORITY: dict[TrafficLight, int] = {"green": 0, "yellow": 1, "red": 2}


@dataclass(frozen=True)
class CampaignDependencies:
    """Injected runtime dependencies for the county campaign pipeline."""

    model: ModelClient
    county_table: dict[str, CountyRecord]
    compliance_config: ComplianceConfig
    verticals_config: VerticalsConfig


class CountyInputDict(TypedDict):
    """Per-county payload passed via LangGraph ``Send`` to the county runner node."""

    fips: str
    vertical: Vertical
    bid_per_lead_usd: float
    cpc_usd: NumericRange
    landing_cvr: NumericRange


class OverallState(TypedDict):
    """Top-level LangGraph state for multi-county fan-out and comparison."""

    county_fips_list: list[str]
    vertical: Vertical
    bid_per_lead_usd: float
    cpc_usd: NumericRange
    landing_cvr: NumericRange
    campaigns: Annotated[list[CountyCampaign], operator.add]
    comparison: CampaignComparison | None


def create_default_dependencies(
    settings: Settings | None = None,
    table_path: Path | None = None,
    compliance_path: Path | None = None,
    verticals_path: Path | None = None,
) -> CampaignDependencies:
    """Build default runtime dependencies from settings and local config/data files."""
    resolved_settings = settings if settings is not None else Settings()

    if resolved_settings.fake_model or resolved_settings.anthropic_api_key is None:
        model: ModelClient = FakeModelClient()
    else:
        model = AnthropicModelClient(resolved_settings.anthropic_api_key.get_secret_value())

    resolved_table_path = (
        table_path
        if table_path is not None
        else resolved_settings.project_root / "data" / "counties.parquet"
    )
    resolved_compliance_path = (
        compliance_path
        if compliance_path is not None
        else resolved_settings.project_root / "config" / "compliance.json"
    )
    resolved_verticals_path = (
        verticals_path
        if verticals_path is not None
        else resolved_settings.project_root / "config" / "verticals.json"
    )

    return CampaignDependencies(
        model=model,
        county_table=load_county_table(resolved_table_path),
        compliance_config=load_compliance_config(resolved_compliance_path),
        verticals_config=load_verticals_config(resolved_verticals_path),
    )


def _validate_ad_text(
    text: str,
    *,
    max_chars: int,
    label: str,
    compliance: ComplianceConfig,
) -> list[str]:
    """Validate an ad headline or description against length and Fair Housing rules."""
    errors: list[str] = []
    fits, length = check_character_limit(text, max_chars)
    if not fits:
        errors.append(f"{label} exceeds {max_chars} character limit ({length} chars).")
    errors.extend(find_fair_housing_violations(text, compliance))
    return errors


def _validate_landing_page_fields(
    *,
    headline: str,
    subheadline: str,
    cta_text: str,
    bullet_points: list[str],
    consent_disclosure: str,
    compliance: ComplianceConfig,
) -> list[tuple[str, str, str]]:
    """Return ``(item_id, current_text, reason)`` tuples for any invalid landing page field."""
    failures: list[tuple[str, str, str]] = []

    named_fields: list[tuple[str, str]] = [
        ("lp_headline", headline),
        ("lp_subheadline", subheadline),
        ("lp_cta_text", cta_text),
        *[(f"lp_bullet_{idx}", bullet) for idx, bullet in enumerate(bullet_points, start=1)],
    ]
    for item_id, value in named_fields:
        violations = find_fair_housing_violations(value, compliance)
        if violations:
            failures.append((item_id, value, "; ".join(violations)))

    consent_errors = list(find_fair_housing_violations(consent_disclosure, compliance))
    missing_phrases = validate_consent_disclosure(consent_disclosure, compliance)
    if missing_phrases:
        consent_errors.append(
            f"Consent disclosure missing required TCPA phrase(s): {', '.join(missing_phrases)}."
        )
    if consent_errors:
        failures.append(("lp_consent_disclosure", consent_disclosure, "; ".join(consent_errors)))

    return failures


def _validate_sms_text(
    text: str,
    brand_name: str,
    compliance: ComplianceConfig,
) -> list[str]:
    """Validate an SMS message against TCPA and Fair Housing rules."""
    errors = validate_sms(text, brand_name, compliance)
    errors.extend(find_fair_housing_violations(text, compliance))
    return errors


def _validate_email_fields(
    *,
    email_index: int,
    subject: str,
    body: str,
    compliance: ComplianceConfig,
) -> list[tuple[str, str, str]]:
    """Return ``(item_id, current_text, reason)`` tuples for Fair Housing violations in an email."""
    failures: list[tuple[str, str, str]] = []
    subject_violations = find_fair_housing_violations(subject, compliance)
    if subject_violations:
        failures.append((f"email_{email_index}_subject", subject, "; ".join(subject_violations)))
    body_violations = find_fair_housing_violations(body, compliance)
    if body_violations:
        failures.append((f"email_{email_index}_body", body, "; ".join(body_violations)))
    return failures


def _interpret_and_verify_facts(
    county: CountyRecord,
    vertical_config: VerticalConfig,
    deps: CampaignDependencies,
) -> tuple[list[NumericFact], list[NumericCorrection]]:
    """Run trigger interpretation and verify every numeric claim against the county record."""
    trigger_output = deps.model.interpret_triggers(county, vertical_config)
    raw_facts = [
        NumericFact(
            claim=item.claim,
            field=item.field,
            value=item.value,
            source=item.source,
            status="unverified",
        )
        for item in trigger_output.triggers
    ]
    return verify_numeric_facts(raw_facts, county)


def _draft_and_validate_ads_and_lp(
    county_name: str,
    vertical_config: VerticalConfig,
    grounded_facts: list[NumericFact],
    deps: CampaignDependencies,
) -> tuple[AdCopy, LandingPageTop, list[tuple[str, str]]]:
    """Draft ads and landing page copy, validate compliance, and collect failed items."""
    compliance = deps.compliance_config
    draft = deps.model.draft_ads_and_lp(county_name, vertical_config, grounded_facts)
    failed_items: list[tuple[str, str]] = []

    headlines: list[AdHeadline] = []
    for idx, raw_text in enumerate(draft.headlines, start=1):
        text = normalize_nfc(raw_text)
        errors = _validate_ad_text(
            text,
            max_chars=compliance.character_limits.headline,
            label="Headline",
            compliance=compliance,
        )
        if errors:
            reason = "; ".join(errors)
            headlines.append(AdHeadline(text=text, status="rejected", rejection_reason=reason))
            failed_items.append((f"headline_{idx}", f"Current text: {text!r}. Reason: {reason}"))
        else:
            headlines.append(AdHeadline(text=text, status="approved"))

    descriptions: list[AdDescription] = []
    for idx, raw_text in enumerate(draft.descriptions, start=1):
        text = normalize_nfc(raw_text)
        errors = _validate_ad_text(
            text,
            max_chars=compliance.character_limits.description,
            label="Description",
            compliance=compliance,
        )
        if errors:
            reason = "; ".join(errors)
            descriptions.append(
                AdDescription(text=text, status="rejected", rejection_reason=reason)
            )
            failed_items.append((f"description_{idx}", f"Current text: {text!r}. Reason: {reason}"))
        else:
            descriptions.append(AdDescription(text=text, status="approved"))

    lp_headline = normalize_nfc(draft.lp_headline)
    lp_subheadline = normalize_nfc(draft.lp_subheadline)
    lp_cta_text = normalize_nfc(draft.cta_text)
    lp_bullets = [normalize_nfc(bullet) for bullet in draft.bullet_points]
    lp_consent = normalize_nfc(draft.consent_disclosure)

    lp_failures = _validate_landing_page_fields(
        headline=lp_headline,
        subheadline=lp_subheadline,
        cta_text=lp_cta_text,
        bullet_points=lp_bullets,
        consent_disclosure=lp_consent,
        compliance=compliance,
    )
    for item_id, current_text, reason in lp_failures:
        failed_items.append((item_id, f"Current text: {current_text!r}. Reason: {reason}"))

    lp_status: AssetStatus = "rejected" if lp_failures else "approved"
    lp_reason = "; ".join(reason for _, _, reason in lp_failures) if lp_failures else None
    landing_page = LandingPageTop(
        headline=lp_headline,
        subheadline=lp_subheadline,
        cta_text=lp_cta_text,
        bullet_points=lp_bullets,
        consent_disclosure=lp_consent,
        status=lp_status,
        rejection_reason=lp_reason,
    )

    return AdCopy(headlines=headlines, descriptions=descriptions), landing_page, failed_items


def _draft_and_validate_followup(
    county_name: str,
    vertical_config: VerticalConfig,
    grounded_facts: list[NumericFact],
    deps: CampaignDependencies,
) -> tuple[list[SMSMessage], list[EmailFollowup], list[tuple[str, str]]]:
    """Draft SMS and email follow-ups, validate TCPA/Fair Housing, and collect failed items."""
    compliance = deps.compliance_config
    draft = deps.model.draft_followup(county_name, vertical_config.brand_name, grounded_facts)
    failed_items: list[tuple[str, str]] = []

    sms_messages: list[SMSMessage] = []
    for idx, raw_sms in enumerate(draft.sms_messages, start=1):
        text = normalize_nfc(raw_sms)
        errors = _validate_sms_text(text, vertical_config.brand_name, compliance)
        if errors:
            reason = "; ".join(errors)
            sms_messages.append(
                SMSMessage(
                    message_index=idx,
                    text=text,
                    char_count=len(text),
                    status="rejected",
                    rejection_reason=reason,
                )
            )
            failed_items.append((f"sms_{idx}", f"Current text: {text!r}. Reason: {reason}"))
        else:
            sms_messages.append(
                SMSMessage(
                    message_index=idx,
                    text=text,
                    char_count=len(text),
                    status="approved",
                )
            )

    email_followups: list[EmailFollowup] = []
    for idx, email in enumerate(draft.emails, start=1):
        subject = normalize_nfc(email.subject)
        body = normalize_nfc(email.body)
        failures = _validate_email_fields(
            email_index=idx,
            subject=subject,
            body=body,
            compliance=compliance,
        )
        for item_id, current_text, reason in failures:
            failed_items.append((item_id, f"Current text: {current_text!r}. Reason: {reason}"))
        if failures:
            email_followups.append(
                EmailFollowup(
                    email_index=idx,
                    subject=subject,
                    body=body,
                    status="rejected",
                    rejection_reason="; ".join(reason for _, _, reason in failures),
                )
            )
        else:
            email_followups.append(
                EmailFollowup(
                    email_index=idx,
                    subject=subject,
                    body=body,
                    status="approved",
                )
            )

    return sms_messages, email_followups, failed_items


def _regenerate_failed_assets(
    *,
    county_name: str,
    vertical_config: VerticalConfig,
    ad_copy: AdCopy,
    landing_page: LandingPageTop,
    sms_messages: list[SMSMessage],
    email_followups: list[EmailFollowup],
    failed_items: list[tuple[str, str]],
    deps: CampaignDependencies,
) -> tuple[AdCopy, LandingPageTop, list[SMSMessage], list[EmailFollowup]]:
    """Regenerate failed assets once and re-validate every rewritten item."""
    if not failed_items:
        return ad_copy, landing_page, sms_messages, email_followups

    compliance = deps.compliance_config
    regen_output = deps.model.regenerate_assets(
        county_name=county_name,
        brand_name=vertical_config.brand_name,
        failed_items=failed_items,
        vertical_config=vertical_config,
    )
    regen_map = {item.item_id: normalize_nfc(item.text) for item in regen_output.assets}

    updated_headlines: list[AdHeadline] = []
    for idx, headline in enumerate(ad_copy.headlines, start=1):
        item_id = f"headline_{idx}"
        if headline.status != "rejected" or item_id not in regen_map:
            updated_headlines.append(headline)
            continue
        candidate = regen_map[item_id]
        errors = _validate_ad_text(
            candidate,
            max_chars=compliance.character_limits.headline,
            label="Headline",
            compliance=compliance,
        )
        if errors:
            updated_headlines.append(
                AdHeadline(text=candidate, status="rejected", rejection_reason="; ".join(errors))
            )
        else:
            updated_headlines.append(
                AdHeadline(text=candidate, status="regenerated", rejection_reason=None)
            )

    updated_descriptions: list[AdDescription] = []
    for idx, description in enumerate(ad_copy.descriptions, start=1):
        item_id = f"description_{idx}"
        if description.status != "rejected" or item_id not in regen_map:
            updated_descriptions.append(description)
            continue
        candidate = regen_map[item_id]
        errors = _validate_ad_text(
            candidate,
            max_chars=compliance.character_limits.description,
            label="Description",
            compliance=compliance,
        )
        if errors:
            updated_descriptions.append(
                AdDescription(text=candidate, status="rejected", rejection_reason="; ".join(errors))
            )
        else:
            updated_descriptions.append(
                AdDescription(text=candidate, status="regenerated", rejection_reason=None)
            )

    updated_lp = landing_page
    if landing_page.status == "rejected":
        lp_headline = regen_map.get("lp_headline", landing_page.headline)
        lp_subheadline = regen_map.get("lp_subheadline", landing_page.subheadline)
        lp_cta_text = regen_map.get("lp_cta_text", landing_page.cta_text)
        lp_bullets = [
            regen_map.get(f"lp_bullet_{idx}", bullet)
            for idx, bullet in enumerate(landing_page.bullet_points, start=1)
        ]
        lp_consent = regen_map.get("lp_consent_disclosure", landing_page.consent_disclosure)

        lp_failures = _validate_landing_page_fields(
            headline=lp_headline,
            subheadline=lp_subheadline,
            cta_text=lp_cta_text,
            bullet_points=lp_bullets,
            consent_disclosure=lp_consent,
            compliance=compliance,
        )
        if lp_failures:
            updated_lp = LandingPageTop(
                headline=lp_headline,
                subheadline=lp_subheadline,
                cta_text=lp_cta_text,
                bullet_points=lp_bullets,
                consent_disclosure=lp_consent,
                status="rejected",
                rejection_reason="; ".join(reason for _, _, reason in lp_failures),
            )
        else:
            updated_lp = LandingPageTop(
                headline=lp_headline,
                subheadline=lp_subheadline,
                cta_text=lp_cta_text,
                bullet_points=lp_bullets,
                consent_disclosure=lp_consent,
                status="regenerated",
                rejection_reason=None,
            )

    updated_sms: list[SMSMessage] = []
    for sms in sms_messages:
        item_id = f"sms_{sms.message_index}"
        if sms.status != "rejected" or item_id not in regen_map:
            updated_sms.append(sms)
            continue
        candidate = regen_map[item_id]
        errors = _validate_sms_text(candidate, vertical_config.brand_name, compliance)
        if errors:
            updated_sms.append(
                SMSMessage(
                    message_index=sms.message_index,
                    text=candidate,
                    char_count=len(candidate),
                    status="rejected",
                    rejection_reason="; ".join(errors),
                )
            )
        else:
            updated_sms.append(
                SMSMessage(
                    message_index=sms.message_index,
                    text=candidate,
                    char_count=len(candidate),
                    status="regenerated",
                    rejection_reason=None,
                )
            )

    updated_emails: list[EmailFollowup] = []
    for email in email_followups:
        if email.status != "rejected":
            updated_emails.append(email)
            continue
        subject = regen_map.get(f"email_{email.email_index}_subject", email.subject)
        body = regen_map.get(f"email_{email.email_index}_body", email.body)
        failures = _validate_email_fields(
            email_index=email.email_index,
            subject=subject,
            body=body,
            compliance=compliance,
        )
        if failures:
            updated_emails.append(
                EmailFollowup(
                    email_index=email.email_index,
                    subject=subject,
                    body=body,
                    status="rejected",
                    rejection_reason="; ".join(reason for _, _, reason in failures),
                )
            )
        else:
            updated_emails.append(
                EmailFollowup(
                    email_index=email.email_index,
                    subject=subject,
                    body=body,
                    status="regenerated",
                    rejection_reason=None,
                )
            )

    return (
        AdCopy(headlines=updated_headlines, descriptions=updated_descriptions),
        updated_lp,
        updated_sms,
        updated_emails,
    )


def _build_human_review_list(
    *,
    facts: list[NumericFact],
    assets: CampaignAssets,
    missing_topics: list[str],
    compliance: ComplianceConfig,
) -> list[HumanReviewItem]:
    """Collect copy review triggers, unverified numeric facts, and rejected/missing assets."""
    items: list[HumanReviewItem] = []

    for idx, headline in enumerate(assets.ad_copy.headlines, start=1):
        name = f"headline_{idx}"
        items.extend(detect_human_review_triggers(headline.text, name, compliance))
        if headline.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item=name,
                    reason=headline.rejection_reason or f"Asset status is {headline.status}.",
                    rule_id=f"asset-{headline.status}",
                )
            )

    for idx, description in enumerate(assets.ad_copy.descriptions, start=1):
        name = f"description_{idx}"
        items.extend(detect_human_review_triggers(description.text, name, compliance))
        if description.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item=name,
                    reason=description.rejection_reason or f"Asset status is {description.status}.",
                    rule_id=f"asset-{description.status}",
                )
            )

    if assets.landing_page is None:
        items.append(
            HumanReviewItem(
                item="landing_page",
                reason="Landing page asset is missing.",
                rule_id="asset-missing",
            )
        )
    else:
        lp = assets.landing_page
        lp_fields: list[tuple[str, str]] = [
            ("lp_headline", lp.headline),
            ("lp_subheadline", lp.subheadline),
            ("lp_cta_text", lp.cta_text),
            *[(f"lp_bullet_{idx}", bullet) for idx, bullet in enumerate(lp.bullet_points, start=1)],
            ("lp_consent_disclosure", lp.consent_disclosure),
        ]
        for field_name, field_text in lp_fields:
            items.extend(detect_human_review_triggers(field_text, field_name, compliance))
        if lp.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item="landing_page",
                    reason=lp.rejection_reason or f"Asset status is {lp.status}.",
                    rule_id=f"asset-{lp.status}",
                )
            )

    for sms in assets.sms_messages:
        name = f"sms_{sms.message_index}"
        items.extend(detect_human_review_triggers(sms.text, name, compliance))
        if sms.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item=name,
                    reason=sms.rejection_reason or f"Asset status is {sms.status}.",
                    rule_id=f"asset-{sms.status}",
                )
            )

    for email in assets.email_followups:
        name = f"email_{email.email_index}"
        items.extend(
            detect_human_review_triggers(f"{email.subject}\n{email.body}", name, compliance)
        )
        if email.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item=name,
                    reason=email.rejection_reason or f"Asset status is {email.status}.",
                    rule_id=f"asset-{email.status}",
                )
            )

    for question in assets.questions:
        name = f"question_{question.question_index}"
        items.extend(detect_human_review_triggers(question.question, name, compliance))
        if question.status in ("rejected", "missing"):
            items.append(
                HumanReviewItem(
                    item=name,
                    reason=question.rejection_reason or f"Asset status is {question.status}.",
                    rule_id=f"asset-{question.status}",
                )
            )

    if not assets.questions:
        items.append(
            HumanReviewItem(
                item="questions",
                reason="Qualification questions are missing.",
                rule_id="asset-missing",
            )
        )
    if not assets.ad_copy.headlines:
        items.append(
            HumanReviewItem(
                item="ad_headlines",
                reason="Ad headlines are missing.",
                rule_id="asset-missing",
            )
        )
    if not assets.ad_copy.descriptions:
        items.append(
            HumanReviewItem(
                item="ad_descriptions",
                reason="Ad descriptions are missing.",
                rule_id="asset-missing",
            )
        )
    if not assets.sms_messages:
        items.append(
            HumanReviewItem(
                item="sms_messages",
                reason="SMS follow-up messages are missing.",
                rule_id="asset-missing",
            )
        )
    if not assets.email_followups:
        items.append(
            HumanReviewItem(
                item="email_followups",
                reason="Email follow-up messages are missing.",
                rule_id="asset-missing",
            )
        )

    for topic in missing_topics:
        items.append(
            HumanReviewItem(
                item=f"qualification_topic:{topic}",
                reason=f"Required qualification topic '{topic}' was not covered.",
                rule_id="missing-qualification-topic",
            )
        )

    for fact in facts:
        if fact.status == "unverified":
            items.append(
                HumanReviewItem(
                    item=f"fact:{fact.field}",
                    reason=(
                        f"Numeric claim '{fact.claim}' (value={fact.value}) "
                        "could not be verified against county data."
                    ),
                    rule_id="unverified-numeric-fact",
                )
            )

    return items


def _fallback_unit_economics(county_input: CountyInputDict, reason: str) -> UnitEconomics:
    """Return a safe fallback UnitEconomics object when unit economics cannot be computed."""
    return UnitEconomics(
        bid_per_lead_usd=county_input["bid_per_lead_usd"],
        cpl_best_usd=0.0,
        cpl_worst_usd=0.0,
        max_cpc_usd=0.0,
        verdict="red",
        explanation=f"Unit economics unavailable: {reason}",
    )


def run_county_pipeline(
    county_input: CountyInputDict,
    deps: CampaignDependencies,
) -> CountyCampaign:
    """Execute the full single-county verification, drafting, compliance, and economics pipeline."""
    fips = county_input["fips"]
    vertical = county_input["vertical"]
    county_name = f"Unknown ({fips})"
    unit_economics: UnitEconomics | None = None

    try:
        unit_economics = calculate_unit_economics(
            county_input["bid_per_lead_usd"],
            county_input["cpc_usd"],
            county_input["landing_cvr"],
        )

        county = deps.county_table.get(fips)
        if county is None:
            return CountyCampaign(
                county_fips=fips,
                county_name=county_name,
                vertical=vertical,
                status="failed",
                error_message="FIPS not found in county table",
                unit_economics=unit_economics,
            )

        county_name = county.county_name
        vertical_config = deps.verticals_config.verticals.get(vertical)
        if vertical_config is None:
            return CountyCampaign(
                county_fips=fips,
                county_name=county_name,
                vertical=vertical,
                status="failed",
                error_message=f"Unknown vertical: {vertical}",
                unit_economics=unit_economics,
            )

        facts, corrections = _interpret_and_verify_facts(county, vertical_config, deps)
        grounded_facts = [fact for fact in facts if fact.status != "unverified"]

        qual_output = deps.model.draft_qualification(
            county.county_name,
            vertical_config,
            grounded_facts,
        )
        questions: list[QualificationQuestion]
        questions, missing_topics = match_qualification_questions(
            [item.question for item in qual_output.questions],
            vertical_config,
        )

        ad_copy, landing_page, ad_lp_failures = _draft_and_validate_ads_and_lp(
            county.county_name,
            vertical_config,
            grounded_facts,
            deps,
        )
        sms_messages, email_followups, followup_failures = _draft_and_validate_followup(
            county.county_name,
            vertical_config,
            grounded_facts,
            deps,
        )

        failed_items = [*ad_lp_failures, *followup_failures]
        if failed_items:
            ad_copy, landing_page, sms_messages, email_followups = _regenerate_failed_assets(
                county_name=county.county_name,
                vertical_config=vertical_config,
                ad_copy=ad_copy,
                landing_page=landing_page,
                sms_messages=sms_messages,
                email_followups=email_followups,
                failed_items=failed_items,
                deps=deps,
            )

        assets = CampaignAssets(
            questions=questions,
            ad_copy=ad_copy,
            landing_page=landing_page,
            sms_messages=sms_messages,
            email_followups=email_followups,
        )
        needs_human_review = _build_human_review_list(
            facts=facts,
            assets=assets,
            missing_topics=missing_topics,
            compliance=deps.compliance_config,
        )

        return CountyCampaign(
            county_fips=county.fips,
            county_name=county.county_name,
            vertical=vertical,
            status="success",
            facts=facts,
            corrections=corrections,
            unit_economics=unit_economics,
            assets=assets,
            needs_human_review=needs_human_review,
        )
    except Exception as exc:
        resolved_econ = (
            unit_economics
            if unit_economics is not None
            else _fallback_unit_economics(county_input, str(exc))
        )
        return CountyCampaign(
            county_fips=fips,
            county_name=county_name,
            vertical=vertical,
            status="failed",
            error_message=str(exc),
            unit_economics=resolved_econ,
        )


def _summarize_campaign(campaign: CountyCampaign) -> str:
    """Format a grounded text summary of a CountyCampaign for cross-county comparison."""
    econ = campaign.unit_economics
    if campaign.status == "failed":
        return (
            f"County: {campaign.county_name} (FIPS {campaign.county_fips}) | "
            f"Status: failed | Error: {campaign.error_message or 'Unknown error'} | "
            f"Unit Economics: verdict={econ.verdict}, bid=${econ.bid_per_lead_usd:.2f}, "
            f"cpl_best=${econ.cpl_best_usd:.2f}, cpl_worst=${econ.cpl_worst_usd:.2f}, "
            f"max_cpc=${econ.max_cpc_usd:.2f}"
        )

    fact_lines = "; ".join(
        f"{fact.claim} [{fact.field}={fact.value}, {fact.status}, {fact.source}]"
        for fact in campaign.facts
    )
    return (
        f"County: {campaign.county_name} (FIPS {campaign.county_fips}) | "
        f"Vertical: {campaign.vertical} | Status: {campaign.status} | "
        f"Unit Economics: verdict={econ.verdict}, bid=${econ.bid_per_lead_usd:.2f}, "
        f"cpl_best=${econ.cpl_best_usd:.2f}, cpl_worst=${econ.cpl_worst_usd:.2f}, "
        f"max_cpc=${econ.max_cpc_usd:.2f} ({econ.explanation}) | "
        f"Facts: {fact_lines or 'None'} | "
        f"Corrections: {len(campaign.corrections)} | "
        f"Human review items: {len(campaign.needs_human_review)}"
    )


def _fallback_comparison(campaigns: list[CountyCampaign], note: str) -> CampaignComparison:
    """Build a deterministic comparison when LLM comparison cannot run."""
    successful = [campaign for campaign in campaigns if campaign.status == "success"]
    if not successful:
        return CampaignComparison(
            campaigns=campaigns,
            recommended_county_fips=None,
            summary=note,
        )

    best = min(
        successful,
        key=lambda c: (
            _VERDICT_PRIORITY[c.unit_economics.verdict],
            c.unit_economics.cpl_worst_usd,
        ),
    )
    return CampaignComparison(
        campaigns=campaigns,
        recommended_county_fips=best.county_fips,
        summary=(
            f"Recommended county: {best.county_name} (FIPS {best.county_fips}) "
            f"with verdict {best.unit_economics.verdict} and worst-case CPL "
            f"${best.unit_economics.cpl_worst_usd:.2f}. ({note})"
        ),
    )


def fan_out_counties(state: OverallState) -> list[Send]:
    """Fan out each target county FIPS into an independent ``run_county`` graph branch."""
    return [
        Send(
            "run_county",
            {
                "fips": fips,
                "vertical": state["vertical"],
                "bid_per_lead_usd": state["bid_per_lead_usd"],
                "cpc_usd": state["cpc_usd"],
                "landing_cvr": state["landing_cvr"],
            },
        )
        for fips in state["county_fips_list"]
    ]


def compile_campaign_graph(
    deps: CampaignDependencies,
) -> CompiledStateGraph[OverallState, None, OverallState, OverallState]:
    """Compile the multi-county LangGraph workflow with ``Send`` fan-out and comparison."""

    def run_county_node(state: CountyInputDict) -> dict[str, list[CountyCampaign]]:
        campaign = run_county_pipeline(state, deps)
        return {"campaigns": [campaign]}

    def compare_counties_node(state: OverallState) -> dict[str, CampaignComparison]:
        order_index = {fips: idx for idx, fips in enumerate(state["county_fips_list"])}
        ordered_campaigns = sorted(
            state["campaigns"],
            key=lambda c: order_index.get(c.county_fips, len(order_index)),
        )
        successful = [campaign for campaign in ordered_campaigns if campaign.status == "success"]
        if not successful:
            return {
                "comparison": _fallback_comparison(
                    ordered_campaigns,
                    "All county pipelines failed; no launch county recommended.",
                )
            }

        summaries = [_summarize_campaign(campaign) for campaign in ordered_campaigns]
        try:
            comp_output = deps.model.compare_counties(summaries)
        except LlmError as exc:
            return {
                "comparison": _fallback_comparison(
                    ordered_campaigns,
                    f"LLM comparison unavailable: {exc}",
                )
            }

        recommended = comp_output.recommended_county_fips.strip() or None
        return {
            "comparison": CampaignComparison(
                campaigns=ordered_campaigns,
                recommended_county_fips=recommended,
                summary=comp_output.summary,
            )
        }

    builder: StateGraph[OverallState, None, OverallState, OverallState] = StateGraph(OverallState)
    builder.add_node("run_county", run_county_node)
    builder.add_node("compare_counties", compare_counties_node)
    builder.add_conditional_edges(START, fan_out_counties, ["run_county"])
    builder.add_edge("run_county", "compare_counties")
    builder.add_edge("compare_counties", END)
    return builder.compile()


def run_campaign(input_data: CampaignInput, deps: CampaignDependencies) -> CountyCampaign:
    """Run the campaign pipeline for a single county."""
    county_input: CountyInputDict = {
        "fips": input_data.county_fips,
        "vertical": input_data.vertical,
        "bid_per_lead_usd": input_data.bid_per_lead_usd,
        "cpc_usd": input_data.cpc_usd,
        "landing_cvr": input_data.landing_cvr,
    }
    return run_county_pipeline(county_input, deps)


def run_multi_campaign(
    input_data: MultiCountyInput,
    deps: CampaignDependencies,
) -> CampaignComparison:
    """Run the multi-county campaign graph and return the cross-county comparison."""
    graph = compile_campaign_graph(deps)
    initial_state: OverallState = {
        "county_fips_list": list(input_data.county_fips_list),
        "vertical": input_data.vertical,
        "bid_per_lead_usd": input_data.bid_per_lead_usd,
        "cpc_usd": input_data.cpc_usd,
        "landing_cvr": input_data.landing_cvr,
        "campaigns": [],
        "comparison": None,
    }
    final_state = graph.invoke(initial_state)
    comparison = final_state.get("comparison")
    if isinstance(comparison, CampaignComparison):
        return comparison
    campaigns = final_state.get("campaigns")
    resolved_campaigns = campaigns if isinstance(campaigns, list) else []
    return CampaignComparison(
        campaigns=resolved_campaigns,
        recommended_county_fips=None,
        summary="Comparison was not produced by the campaign graph.",
    )
