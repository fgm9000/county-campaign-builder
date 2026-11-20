"""LLM client protocol, structured output DTOs, deterministic fake, and Anthropic client."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Final, Protocol

import anthropic
import httpx
from anthropic.types import TextBlock
from pydantic import ValidationError

from county_campaign_builder.county_data import COUNT_COLUMNS, CountyRecord
from county_campaign_builder.domain import QuestionTopic, VerticalConfig
from county_campaign_builder.models import Contract, NumericFact
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

HAIKU_MODEL: Final[str] = "claude-haiku-4-5"
SONNET_MODEL: Final[str] = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS: Final[int] = 2048

DALLAS_FIPS: Final[str] = "48113"
PINELLAS_FIPS: Final[str] = "12103"
COOK_FIPS: Final[str] = "17031"
DALLAS_TRAP_MEDIAN_HOME_VALUE: Final[int] = 350_000

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LlmError(RuntimeError):
    """Base error raised when an LLM request fails or cannot be completed."""


class LlmOutputError(LlmError):
    """Raised when an LLM returns empty, malformed, or schema-invalid output."""


# ---------------------------------------------------------------------------
# Structured Output DTOs
# ---------------------------------------------------------------------------


class TriggerItem(Contract):
    """Single county market trigger grounded in a Census or NOAA statistic."""

    claim: str
    field: str
    value: float | int
    source: str


class TriggerInterpretationOutput(Contract):
    """Structured output for county trigger interpretation."""

    triggers: list[TriggerItem]


class QualificationQuestionItem(Contract):
    """Single lead-qualification intake question."""

    question: str
    topic: str | None = None
    why: str | None = None


class QualificationQuestionsOutput(Contract):
    """Structured output for lead-qualification questions."""

    questions: list[QualificationQuestionItem]


class AdsAndLandingPageOutput(Contract):
    """Structured output for responsive search ads and above-the-fold landing page copy."""

    headlines: list[str]
    descriptions: list[str]
    lp_headline: str
    lp_subheadline: str
    cta_text: str
    bullet_points: list[str]
    consent_disclosure: str


class EmailItem(Contract):
    """Single follow-up email asset."""

    subject: str
    body: str


class FollowupOutput(Contract):
    """Structured output for SMS and email follow-up sequences."""

    sms_messages: list[str]
    emails: list[EmailItem]


class RegeneratedAssetItem(Contract):
    """Single rewritten asset returned by targeted regeneration."""

    item_id: str
    text: str


class RegenerateOutput(Contract):
    """Structured output for targeted asset regeneration."""

    assets: list[RegeneratedAssetItem]


class ComparisonOutput(Contract):
    """Structured output for multi-county executive comparison."""

    recommended_county_fips: str
    summary: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ModelClient(Protocol):
    """Interface for structured campaign generation and county comparison."""

    def interpret_triggers(
        self,
        county: CountyRecord,
        vertical_config: VerticalConfig,
    ) -> TriggerInterpretationOutput: ...

    def draft_qualification(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> QualificationQuestionsOutput: ...

    def draft_ads_and_lp(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> AdsAndLandingPageOutput: ...

    def draft_followup(
        self,
        county_name: str,
        brand_name: str,
        verified_facts: Sequence[NumericFact],
    ) -> FollowupOutput: ...

    def regenerate_assets(
        self,
        county_name: str,
        brand_name: str,
        failed_items: Sequence[tuple[str, str]],
        vertical_config: VerticalConfig,
    ) -> RegenerateOutput: ...

    def compare_counties(
        self,
        campaign_summaries: Sequence[str],
    ) -> ComparisonOutput: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_for_field(field: str) -> str:
    return NOAA_SOURCE if field in COUNT_COLUMNS else CENSUS_SOURCE


def _short_county_name(county_name: str) -> str:
    return county_name.split(",", maxsplit=1)[0].replace(" County", "").strip() or "Local"


def _fit_text(candidate: str, fallback: str, max_chars: int) -> str:
    if len(candidate) <= max_chars:
        return candidate
    if len(fallback) <= max_chars:
        return fallback
    return fallback[:max_chars].rstrip()


def _format_trigger_claim(field: str, value: float | int, county: CountyRecord) -> str:
    templates: dict[str, str] = {
        "hail_reports_1in": (f"{value} hail reports of 1 inch or larger in {county.years_covered}"),
        "severe_wind_reports": (
            f"{value} severe thunderstorm wind reports (50+ kt) in {county.years_covered}"
        ),
        "tornado_events": f"{value} tornado events recorded in {county.years_covered}",
        "tropical_events": f"{value} tropical storm or hurricane events in {county.years_covered}",
        "median_year_built": (f"Median home construction year is {value} in {county.county_name}"),
        "owner_occupied_pct": (
            f"{value}% of households are owner-occupied in {county.county_name}"
        ),
        "vacancy_pct": f"{value}% housing vacancy rate in {county.county_name}",
        "median_home_value_usd": (f"Median home value is ${int(value):,} in {county.county_name}"),
        "owner_long_tenure_pct": (f"{value}% of owner-occupied households moved in before 2000"),
        "free_and_clear_pct": f"{value}% of owner-occupied homes are owned free and clear",
    }
    return templates.get(field, f"{field.replace('_', ' ')} is {value} in {county.county_name}")


def _trigger_from_county(county: CountyRecord, field: str) -> TriggerItem | None:
    raw_val: object = getattr(county, field, None)
    if raw_val is None or isinstance(raw_val, bool) or not isinstance(raw_val, int | float):
        return None
    return TriggerItem(
        claim=_format_trigger_claim(field, raw_val, county),
        field=field,
        value=raw_val,
        source=_source_for_field(field),
    )


def _question_for_topic(topic: QuestionTopic, county_name: str) -> QualificationQuestionItem:
    topic_questions: dict[str, str] = {
        "timeline": f"How soon are you hoping to sell your property in {county_name}?",
        "property_condition": (
            "What is the overall condition of the home, and are there any major repairs needed?"
        ),
        "listed_with_agent": (
            "Is the property currently listed with a real estate agent or on the MLS?"
        ),
        "decision_maker": (
            "Are you the sole owner on the title, or are other co-owners part of the decision?"
        ),
        "reason_for_selling": (
            "What is your primary reason for selling right now "
            "(such as relocation, inheritance, or managing tenants)?"
        ),
        "homeowner": f"Do you own the property in {county_name}, or do you rent?",
        "roof_age": "Approximately how old is your roof, or when was it last installed?",
        "damage_type": (
            "Have you noticed hail damage, wind damage, missing shingles, or an active leak?"
        ),
        "replacement_vs_repair": (
            "Are you looking for a full roof replacement or a targeted repair?"
        ),
        "insurance_claim": (
            "Have you already opened an insurance claim or spoken with an adjuster?"
        ),
    }
    question = topic_questions.get(
        topic.topic,
        f"Can you share details regarding {topic.topic.replace('_', ' ')} for your "
        f"{county_name} property?",
    )
    return QualificationQuestionItem(
        question=question,
        topic=topic.topic,
        why=topic.why,
    )


def _is_roofing_vertical(vertical_config: VerticalConfig) -> bool:
    label_lower = vertical_config.label.lower()
    first_field = vertical_config.trigger_fields[0] if vertical_config.trigger_fields else ""
    return "roof" in label_lower or first_field == "hail_reports_1in"


def _build_compliant_sms(brand_name: str, body: str) -> str:
    suffix = "Reply STOP to opt out."
    prefix = f"{brand_name}: "
    available = SMS_MAX_CHARS - len(prefix) - len(suffix) - 1
    if available <= 0:
        minimal = f"{brand_name} {suffix}"
        return minimal[:SMS_MAX_CHARS]
    if len(body) <= available:
        return f"{prefix}{body} {suffix}"
    trimmed_body = body[: max(0, available - 3)].rstrip() + "..."
    return f"{prefix}{trimmed_body} {suffix}"


def _extract_json_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    fence_pattern = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    if fence_pattern is not None:
        return fence_pattern.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _build_json_system_prompt(schema: dict[str, object]) -> str:
    schema_json = json.dumps(schema, ensure_ascii=True)
    return (
        "You must respond with ONLY a single valid JSON object and no surrounding prose or "
        "markdown fences. Never use unescaped double quotes inside string values (use single "
        "quotes or escape them with a backslash). The JSON object MUST conform strictly to this "
        f"JSON Schema:\n{schema_json}"
    )


# ---------------------------------------------------------------------------
# Deterministic Fake Implementation
# ---------------------------------------------------------------------------


class FakeModelClient:
    """Deterministic offline ModelClient for CI, tests, and local fake-mode runs."""

    def __init__(self, *, simulate_error: bool = False, plant_trap: bool = True) -> None:
        self._simulate_error = simulate_error
        self._plant_trap = plant_trap

    def _raise_if_error(self) -> None:
        if self._simulate_error:
            raise LlmError("Simulated LLM client failure.")

    def interpret_triggers(
        self,
        county: CountyRecord,
        vertical_config: VerticalConfig,
    ) -> TriggerInterpretationOutput:
        self._raise_if_error()

        triggers: list[TriggerItem] = []
        seen_fields: set[str] = set()

        if county.fips == DALLAS_FIPS and self._plant_trap:
            triggers.append(
                TriggerItem(
                    claim=(
                        f"Median home value is ${DALLAS_TRAP_MEDIAN_HOME_VALUE:,} in "
                        f"{county.county_name}"
                    ),
                    field="median_home_value_usd",
                    value=DALLAS_TRAP_MEDIAN_HOME_VALUE,
                    source=CENSUS_SOURCE,
                )
            )
            seen_fields.add("median_home_value_usd")

        preferred_order = self._preferred_fields_for_county(county.fips, vertical_config)
        for field in preferred_order:
            if field in seen_fields:
                continue
            item = _trigger_from_county(county, field)
            if item is not None:
                triggers.append(item)
                seen_fields.add(field)
            if len(triggers) >= 4:
                break

        return TriggerInterpretationOutput(triggers=triggers)

    @staticmethod
    def _preferred_fields_for_county(fips: str, vertical_config: VerticalConfig) -> list[str]:
        if fips in {PINELLAS_FIPS, COOK_FIPS, DALLAS_FIPS}:
            priority = [
                "median_home_value_usd",
                "free_and_clear_pct",
                "owner_long_tenure_pct",
                "vacancy_pct",
                "median_year_built",
            ]
        else:
            priority = []

        ordered: list[str] = []
        for field in [*priority, *vertical_config.trigger_fields]:
            if field not in ordered:
                ordered.append(field)
        return ordered

    def draft_qualification(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> QualificationQuestionsOutput:
        self._raise_if_error()
        _ = verified_facts
        questions = [
            _question_for_topic(topic, county_name)
            for topic in vertical_config.required_question_topics
        ]
        return QualificationQuestionsOutput(questions=questions)

    def draft_ads_and_lp(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> AdsAndLandingPageOutput:
        self._raise_if_error()
        short = _short_county_name(county_name)
        is_roofing = _is_roofing_vertical(vertical_config)

        if is_roofing:
            headlines = [
                _fit_text(
                    f"{short} Roof Replacement",
                    "Local Roof Replacement",
                    AD_HEADLINE_MAX_CHARS,
                ),
                _fit_text(
                    "Storm Roof Inspections",
                    "Storm Roof Inspections",
                    AD_HEADLINE_MAX_CHARS,
                ),
                _fit_text(
                    "Licensed Local Roofers",
                    "Licensed Local Roofers",
                    AD_HEADLINE_MAX_CHARS,
                ),
            ]
            descriptions = [
                _fit_text(
                    f"Serving {short} homeowners with thorough roof inspections "
                    "and clear estimates.",
                    "Serving local homeowners with thorough roof inspections and clear estimates.",
                    AD_DESCRIPTION_MAX_CHARS,
                ),
                _fit_text(
                    "Full roof replacements built for severe hail and wind weather conditions.",
                    "Full roof replacements built for severe hail and wind weather.",
                    AD_DESCRIPTION_MAX_CHARS,
                ),
            ]
            lp_headline = f"Protect Your {short} Home With a Dependable Roof Replacement"
            lp_subheadline = (
                f"Connect with {vertical_config.brand_name} for a detailed roof assessment "
                f"in {county_name}."
            )
            cta_text = "Request Your Roof Assessment"
            bullet_points = [
                "Full roof replacement engineered for severe storm and hail resilience.",
                "Zero-obligation inspection with complete photographic evidence.",
                "Direct insurance claims assistance and documentation support.",
                f"Licensed, bonded, and insured specialists serving {county_name}.",
            ]
        else:
            headlines = [
                _fit_text(
                    f"Sell Your {short} Home As-Is",
                    "Sell Your Local Home As-Is",
                    AD_HEADLINE_MAX_CHARS,
                ),
                _fit_text(
                    "Fair Cash Offer For Owners",
                    "Fair Cash Offer For Owners",
                    AD_HEADLINE_MAX_CHARS,
                ),
                _fit_text(
                    "Sell Without Repairs Needed",
                    "Sell Without Repairs Needed",
                    AD_HEADLINE_MAX_CHARS,
                ),
            ]
            descriptions = [
                _fit_text(
                    f"Request a straightforward as-is cash offer for your {short} home today.",
                    "Request a straightforward as-is cash offer for your home today.",
                    AD_DESCRIPTION_MAX_CHARS,
                ),
                _fit_text(
                    "Skip cleanouts and showings. Review an offer on your preferred timeline.",
                    "Skip cleanouts and showings. Review an offer on your timeline.",
                    AD_DESCRIPTION_MAX_CHARS,
                ),
            ]
            lp_headline = f"Request a Straightforward As-Is Cash Offer in {county_name}"
            lp_subheadline = (
                f"Work directly with {vertical_config.brand_name} to sell on your timeline "
                "without listing."
            )
            cta_text = "Get My Property Review"
            bullet_points = [
                "Sell 100% as-is — no repairs, cleaning, or staging required.",
                "Zero agent commissions, hidden fees, or closing cost surprises.",
                "Flexible closing timeline on your schedule (as fast as 7–14 days).",
                f"Direct cash offer review with a dedicated {county_name} specialist.",
            ]

        consent_disclosure = (
            f"By submitting this form, you agree to receive automated marketing calls and "
            f"texts from {vertical_config.brand_name} at the number provided. Consent is not a "
            f"condition of any purchase. Reply STOP to opt out."
        )

        return AdsAndLandingPageOutput(
            headlines=headlines,
            descriptions=descriptions,
            lp_headline=lp_headline,
            lp_subheadline=lp_subheadline,
            cta_text=cta_text,
            bullet_points=bullet_points,
            consent_disclosure=consent_disclosure,
        )

    def draft_followup(
        self,
        county_name: str,
        brand_name: str,
        verified_facts: Sequence[NumericFact],
    ) -> FollowupOutput:
        self._raise_if_error()
        short = _short_county_name(county_name)
        _ = verified_facts

        sms_1 = _build_compliant_sms(
            brand_name,
            f"Hi! We received your request for an as-is cash offer in {short}. When can we chat?",
        )
        sms_2 = _build_compliant_sms(
            brand_name,
            f"Still looking to sell your {short} house as-is? Reply with your timeline!",
        )

        emails = [
            EmailItem(
                subject=f"Your as-is property review for {county_name}",
                body=(
                    f"Hello,\n\n"
                    f"Thank you for requesting an as-is review for your {short} property with "
                    f"{brand_name} in {county_name}.\n\n"
                    f"We specialize in straightforward as-is home purchases across {short}:\n"
                    f"• 100% As-Is: No repairs, cleaning, or staging required.\n"
                    f"• Zero Commissions: No agent fees or hidden closing deductions.\n"
                    f"• Your Timeline: Close in as few as 7–14 days or on your schedule.\n\n"
                    f"Reply directly to this email with a convenient time for a brief 5-minute\n"
                    f"call so we can review your property details and prepare your cash offer.\n\n"
                    f"Best regards,\n{brand_name}"
                ),
            ),
            EmailItem(
                subject=f"Checking in on your {short} property sale ({brand_name})",
                body=(
                    f"Hello,\n\n"
                    f"We wanted to follow up on your recent cash offer inquiry with {brand_name}\n"
                    f"for {county_name}.\n\n"
                    f"If you want to sell without retail open houses, bank financing delays,\n"
                    f"or spending thousands out-of-pocket on repairs, we are ready to help.\n\n"
                    f"There is zero obligation. Reply here or share the best number to connect.\n\n"
                    f"Best regards,\n{brand_name}"
                ),
            ),
        ]
        return FollowupOutput(sms_messages=[sms_1, sms_2], emails=emails)

    def regenerate_assets(
        self,
        county_name: str,
        brand_name: str,
        failed_items: Sequence[tuple[str, str]],
        vertical_config: VerticalConfig,
    ) -> RegenerateOutput:
        self._raise_if_error()
        short = _short_county_name(county_name)
        rewritten = [
            RegeneratedAssetItem(
                item_id=item_id,
                text=self._regenerate_item_text(
                    item_id=item_id,
                    short_county=short,
                    county_name=county_name,
                    brand_name=brand_name,
                    vertical_config=vertical_config,
                ),
            )
            for item_id, _details in failed_items
        ]
        return RegenerateOutput(assets=rewritten)

    @staticmethod
    def _regenerate_item_text(
        *,
        item_id: str,
        short_county: str,
        county_name: str,
        brand_name: str,
        vertical_config: VerticalConfig,
    ) -> str:
        item_lower = item_id.lower()
        if "headline" in item_lower and "lp_" not in item_lower:
            return _fit_text(
                f"{short_county} Home Options",
                "Local Home Solutions",
                AD_HEADLINE_MAX_CHARS,
            )
        if "description" in item_lower:
            return _fit_text(
                f"Connect with {brand_name} for clear local options in {short_county}.",
                "Connect with our local team for clear next steps today.",
                AD_DESCRIPTION_MAX_CHARS,
            )
        if "sms" in item_lower:
            return _build_compliant_sms(
                brand_name,
                f"Following up on your {short_county} request. Reply with a good time.",
            )
        if "consent" in item_lower:
            return (
                f"By submitting this form, you agree to receive automated calls and texts from "
                f"{brand_name}. Consent is not a condition of purchase. Reply STOP to opt out."
            )
        return (
            f"{brand_name} serves homeowners in {county_name} for "
            f"{vertical_config.label.lower()} inquiries."
        )

    def compare_counties(self, campaign_summaries: Sequence[str]) -> ComparisonOutput:
        self._raise_if_error()
        has_pinellas = any(
            "12103" in summary or "Pinellas" in summary for summary in campaign_summaries
        )
        pinellas_note = (
            " Pinellas County (12103) ranks second with strong tropical storm and "
            "free-and-clear equity signals, though its auction margin is tighter."
            if has_pinellas
            else ""
        )
        summary = (
            "Dallas County, TX (FIPS 48113) is the recommended launch county. Dallas clears "
            "the auction math with a green unit-economics verdict—its worst-case CPL stays "
            "comfortably below the lead bid with healthy CPC headroom—backed by high hail "
            "and wind exposure plus substantial long-tenure equity. By contrast, Cook County, "
            "IL (FIPS 17031) fails the auction math with a red verdict where expected CPL does "
            f"not close below the target bid.{pinellas_note}"
        )
        return ComparisonOutput(recommended_county_fips=DALLAS_FIPS, summary=summary)


# ---------------------------------------------------------------------------
# Live Anthropic Implementation
# ---------------------------------------------------------------------------


class AnthropicModelClient:
    """Anthropic Messages API implementation of ModelClient with strict Pydantic parsing."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: anthropic.Anthropic | None = None,
        haiku_model: str = HAIKU_MODEL,
        sonnet_model: str = SONNET_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = (
            client if client is not None else anthropic.Anthropic(api_key=api_key, max_retries=4)
        )
        self._haiku_model = haiku_model
        self._sonnet_model = sonnet_model
        self._max_tokens = max_tokens

    def _invoke_structured[OutputT: Contract](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
    ) -> OutputT:
        system_prompt = _build_json_system_prompt(response_model.model_json_schema())
        last_error: Exception | None = None
        for _ in range(2):
            try:
                message = self._client.messages.create(
                    model=model,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
            except (anthropic.APIError, httpx.HTTPError, OSError, TimeoutError) as exc:
                raise LlmError(f"Anthropic API call failed for model '{model}': {exc}") from exc

            text_chunks = [block.text for block in message.content if isinstance(block, TextBlock)]
            if not text_chunks:
                name = response_model.__name__
                raise LlmOutputError(
                    f"Anthropic model '{model}' returned no text blocks for {name}."
                )

            raw_json = _extract_json_text("\n".join(text_chunks))
            try:
                return response_model.model_validate_json(raw_json)
            except ValidationError as exc:
                last_error = exc
                continue

        raise LlmOutputError(
            f"Anthropic output failed validation for {response_model.__name__}: {last_error}"
        ) from last_error

    def interpret_triggers(
        self,
        county: CountyRecord,
        vertical_config: VerticalConfig,
    ) -> TriggerInterpretationOutput:
        prompt = build_trigger_interpretation_prompt(county, vertical_config)
        return self._invoke_structured(
            model=self._haiku_model,
            prompt=prompt,
            response_model=TriggerInterpretationOutput,
        )

    def draft_qualification(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> QualificationQuestionsOutput:
        prompt = build_qualification_prompt(county_name, vertical_config, verified_facts)
        return self._invoke_structured(
            model=self._haiku_model,
            prompt=prompt,
            response_model=QualificationQuestionsOutput,
        )

    def draft_ads_and_lp(
        self,
        county_name: str,
        vertical_config: VerticalConfig,
        verified_facts: Sequence[NumericFact],
    ) -> AdsAndLandingPageOutput:
        prompt = build_ads_and_lp_prompt(county_name, vertical_config, verified_facts)
        return self._invoke_structured(
            model=self._sonnet_model,
            prompt=prompt,
            response_model=AdsAndLandingPageOutput,
        )

    def draft_followup(
        self,
        county_name: str,
        brand_name: str,
        verified_facts: Sequence[NumericFact],
    ) -> FollowupOutput:
        prompt = build_followup_prompt(county_name, brand_name, verified_facts)
        return self._invoke_structured(
            model=self._haiku_model,
            prompt=prompt,
            response_model=FollowupOutput,
        )

    def regenerate_assets(
        self,
        county_name: str,
        brand_name: str,
        failed_items: Sequence[tuple[str, str]],
        vertical_config: VerticalConfig,
    ) -> RegenerateOutput:
        prompt = build_regeneration_prompt(county_name, brand_name, failed_items, vertical_config)
        return self._invoke_structured(
            model=self._sonnet_model,
            prompt=prompt,
            response_model=RegenerateOutput,
        )

    def compare_counties(
        self,
        campaign_summaries: Sequence[str],
    ) -> ComparisonOutput:
        prompt = build_comparison_prompt(campaign_summaries)
        return self._invoke_structured(
            model=self._sonnet_model,
            prompt=prompt,
            response_model=ComparisonOutput,
        )
