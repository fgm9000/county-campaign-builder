"""Deterministic DeepEval metrics for county-level lead-gen campaigns (no LLM calls)."""

from __future__ import annotations

import math
import re
from abc import abstractmethod

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.domain import (
    NUMERIC_ABS_TOLERANCE,
    check_character_limit,
    find_fair_housing_violations,
    match_qualification_questions,
    validate_consent_disclosure,
)
from county_campaign_builder.economics import calculate_unit_economics
from county_campaign_builder.graph import CampaignDependencies
from county_campaign_builder.models import AssetStatus, CampaignInput, CountyCampaign

PASS_THRESHOLD = 1.0
APPROVED_STATUSES: tuple[AssetStatus, ...] = ("approved", "regenerated")


def to_test_case(input_data: CampaignInput, campaign: CountyCampaign) -> LLMTestCase:
    """Serialize a CampaignInput and CountyCampaign pair into a DeepEval LLMTestCase."""
    return LLMTestCase(
        input=input_data.model_dump_json(),
        actual_output=campaign.model_dump_json(),
    )


def _values_match(actual: float | int, expected: float | int) -> bool:
    """Compare numeric values using float tolerance when either side is float, else exact int."""
    if isinstance(expected, float) or isinstance(actual, float):
        return math.isclose(float(actual), float(expected), abs_tol=NUMERIC_ABS_TOLERANCE)
    return int(actual) == int(expected)


class DeterministicMetric(BaseMetric):
    """Pass/fail metric over a CountyCampaign: empty `problems` list means score 1.0."""

    def __init__(self, input_data: CampaignInput, deps: CampaignDependencies) -> None:
        self.input_data = input_data
        self.deps = deps
        self.threshold = PASS_THRESHOLD
        self.async_mode = False
        self.verbose_mode = False
        self.strict_mode = False
        self.include_reason = True

    @abstractmethod
    def problems(self, campaign: CountyCampaign) -> list[str]:
        """Return validation failure reasons for a generated campaign, or empty list."""

    def measure(self, test_case: LLMTestCase, *args: object, **kwargs: object) -> float:
        """Validate the serialized CountyCampaign, record problems, and return 1.0 or 0.0."""
        _ = (args, kwargs)
        campaign = CountyCampaign.model_validate_json(test_case.actual_output or "")
        found = self.problems(campaign)
        self.score = 1.0 if not found else 0.0
        self.reason = "; ".join(found) if found else "ok"
        self.success = self.score >= PASS_THRESHOLD
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: object, **kwargs: object) -> float:
        """Async wrapper delegating to synchronous `measure`."""
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        """Return whether the last measured score met the pass threshold."""
        return self.score is not None and self.score >= PASS_THRESHOLD

    @property
    def __name__(self) -> str:
        return self.__class__.__qualname__


class NumericAccuracyMetric(DeterministicMetric):
    """Every verified/corrected fact matches the county table and corrections record any fixes."""

    def problems(self, campaign: CountyCampaign) -> list[str]:
        county = self.deps.county_table.get(campaign.county_fips)
        if county is None:
            return [f"county_fips {campaign.county_fips!r} not found in county table"]

        found: list[str] = []
        for fact in campaign.facts:
            if fact.status not in ("verified", "corrected"):
                continue

            source_val: object = (
                getattr(county, fact.field) if fact.field in CountyRecord.model_fields else None
            )
            if (
                source_val is None
                or isinstance(source_val, bool)
                or not isinstance(source_val, int | float)
            ):
                found.append(
                    f"fact {fact.field!r} ({fact.status}) has no numeric value in county record"
                )
                continue

            if not _values_match(fact.value, source_val):
                found.append(
                    f"fact {fact.field!r} value {fact.value} != county record {source_val}"
                )

            if fact.status == "corrected":
                has_correction = any(
                    corr.field == fact.field
                    and corr.source_value is not None
                    and _values_match(corr.source_value, source_val)
                    for corr in campaign.corrections
                )
                if not has_correction:
                    found.append(f"corrected fact {fact.field!r} missing from corrections")

        return found


class CharacterLimitMetric(DeterministicMetric):
    """Approved and regenerated headlines (<=30), descriptions (<=90), and SMS (<=160)."""

    def problems(self, campaign: CountyCampaign) -> list[str]:
        limits = self.deps.compliance_config.character_limits
        found: list[str] = []

        for idx, headline in enumerate(campaign.assets.ad_copy.headlines, start=1):
            if headline.status in APPROVED_STATUSES:
                fits, length = check_character_limit(headline.text, limits.headline)
                if not fits:
                    found.append(f"headline_{idx} exceeds {limits.headline} chars ({length})")

        for idx, description in enumerate(campaign.assets.ad_copy.descriptions, start=1):
            if description.status in APPROVED_STATUSES:
                fits, length = check_character_limit(description.text, limits.description)
                if not fits:
                    found.append(f"description_{idx} exceeds {limits.description} chars ({length})")

        for sms in campaign.assets.sms_messages:
            if sms.status in APPROVED_STATUSES:
                fits, length = check_character_limit(sms.text, limits.sms)
                if not fits:
                    found.append(f"sms_{sms.message_index} exceeds {limits.sms} chars ({length})")

        return found


class ComplianceMetric(DeterministicMetric):
    """TCPA on SMS and landing page consent disclosure; Fair Housing across approved assets."""

    def problems(self, campaign: CountyCampaign) -> list[str]:
        vertical_config = self.deps.verticals_config.verticals.get(campaign.vertical)
        if vertical_config is None:
            return [f"unknown vertical {campaign.vertical!r}"]

        compliance = self.deps.compliance_config
        brand_name = vertical_config.brand_name
        found: list[str] = []

        for idx, headline in enumerate(campaign.assets.ad_copy.headlines, start=1):
            if headline.status in APPROVED_STATUSES:
                for violation in find_fair_housing_violations(headline.text, compliance):
                    found.append(f"headline_{idx}: {violation}")

        for idx, description in enumerate(campaign.assets.ad_copy.descriptions, start=1):
            if description.status in APPROVED_STATUSES:
                for violation in find_fair_housing_violations(description.text, compliance):
                    found.append(f"description_{idx}: {violation}")

        landing_page = campaign.assets.landing_page
        if landing_page is not None and landing_page.status in APPROVED_STATUSES:
            lp_fields: list[tuple[str, str]] = [
                ("lp_headline", landing_page.headline),
                ("lp_subheadline", landing_page.subheadline),
                ("lp_cta_text", landing_page.cta_text),
                *[
                    (f"lp_bullet_{idx}", bullet)
                    for idx, bullet in enumerate(landing_page.bullet_points, start=1)
                ],
                ("lp_consent_disclosure", landing_page.consent_disclosure),
            ]
            for field_name, text in lp_fields:
                for violation in find_fair_housing_violations(text, compliance):
                    found.append(f"{field_name}: {violation}")

            missing_phrases = validate_consent_disclosure(
                landing_page.consent_disclosure, compliance
            )
            if missing_phrases:
                found.append(
                    "landing_page consent_disclosure missing TCPA phrase(s): "
                    f"{', '.join(missing_phrases)}"
                )

        for sms in campaign.assets.sms_messages:
            if sms.status in APPROVED_STATUSES:
                if brand_name.lower() not in sms.text.lower():
                    found.append(f"sms_{sms.message_index} missing brand_name {brand_name!r}")
                has_opt_out = any(
                    re.search(rf"\b{re.escape(keyword)}\b", sms.text, re.IGNORECASE)
                    for keyword in compliance.tcpa_sms.opt_out_keywords
                )
                if not has_opt_out:
                    found.append(f"sms_{sms.message_index} missing TCPA opt-out keyword")
                for violation in find_fair_housing_violations(sms.text, compliance):
                    found.append(f"sms_{sms.message_index}: {violation}")

        for email in campaign.assets.email_followups:
            if email.status in APPROVED_STATUSES:
                for field_name, text in (
                    (f"email_{email.email_index}_subject", email.subject),
                    (f"email_{email.email_index}_body", email.body),
                ):
                    for violation in find_fair_housing_violations(text, compliance):
                        found.append(f"{field_name}: {violation}")

        return found


class QualificationCoverageMetric(DeterministicMetric):
    """All required qualification topics for the vertical are covered in campaign questions."""

    def problems(self, campaign: CountyCampaign) -> list[str]:
        vertical_config = self.deps.verticals_config.verticals.get(campaign.vertical)
        if vertical_config is None:
            return [f"unknown vertical {campaign.vertical!r}"]

        active_questions = [
            question.question
            for question in campaign.assets.questions
            if question.status in APPROVED_STATUSES
        ]
        _, missing_topics = match_qualification_questions(active_questions, vertical_config)
        return [f"missing qualification topic: {topic}" for topic in missing_topics]


class EconomicsMetric(DeterministicMetric):
    """Independently recalculates unit economics and verifies CPL, max CPC, and verdict."""

    def problems(self, campaign: CountyCampaign) -> list[str]:
        expected = calculate_unit_economics(
            self.input_data.bid_per_lead_usd,
            self.input_data.cpc_usd,
            self.input_data.landing_cvr,
        )
        actual = campaign.unit_economics
        found: list[str] = []

        if not math.isclose(
            actual.bid_per_lead_usd, expected.bid_per_lead_usd, abs_tol=NUMERIC_ABS_TOLERANCE
        ):
            found.append(
                f"bid_per_lead_usd mismatch: expected {expected.bid_per_lead_usd}, "
                f"got {actual.bid_per_lead_usd}"
            )
        if not math.isclose(
            actual.cpl_best_usd, expected.cpl_best_usd, abs_tol=NUMERIC_ABS_TOLERANCE
        ):
            found.append(
                f"cpl_best_usd mismatch: expected {expected.cpl_best_usd}, "
                f"got {actual.cpl_best_usd}"
            )
        if not math.isclose(
            actual.cpl_worst_usd, expected.cpl_worst_usd, abs_tol=NUMERIC_ABS_TOLERANCE
        ):
            found.append(
                f"cpl_worst_usd mismatch: expected {expected.cpl_worst_usd}, "
                f"got {actual.cpl_worst_usd}"
            )
        if not math.isclose(
            actual.max_cpc_usd, expected.max_cpc_usd, abs_tol=NUMERIC_ABS_TOLERANCE
        ):
            found.append(
                f"max_cpc_usd mismatch: expected {expected.max_cpc_usd}, got {actual.max_cpc_usd}"
            )
        if actual.verdict != expected.verdict:
            found.append(f"verdict mismatch: expected {expected.verdict!r}, got {actual.verdict!r}")

        return found


def deterministic_metrics(
    input_data: CampaignInput,
    deps: CampaignDependencies,
) -> list[BaseMetric]:
    """Return all five deterministic DeepEval metrics bound to the input and dependencies."""
    return [
        NumericAccuracyMetric(input_data, deps),
        CharacterLimitMetric(input_data, deps),
        ComplianceMetric(input_data, deps),
        QualificationCoverageMetric(input_data, deps),
        EconomicsMetric(input_data, deps),
    ]
