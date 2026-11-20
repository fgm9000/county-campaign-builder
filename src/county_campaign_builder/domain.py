"""Pure domain logic, config contracts, and compliance guardrails for county campaigns."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.models import (
    AssetStatus,
    Contract,
    FactStatus,
    HumanReviewItem,
    NumericCorrection,
    NumericFact,
    QualificationQuestion,
)

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPLIANCE_CONFIG_PATH = DEFAULT_PROJECT_ROOT / "config" / "compliance.json"
DEFAULT_VERTICALS_CONFIG_PATH = DEFAULT_PROJECT_ROOT / "config" / "verticals.json"
NUMERIC_ABS_TOLERANCE = 0.01


class CharacterLimits(Contract):
    """Maximum character counts for ad copy and SMS segments."""

    headline: int
    description: int
    sms: int


class FairHousingRule(Contract):
    """Single Fair Housing rule with forbidden regex patterns."""

    rule_id: str
    reference: str
    description: str
    forbidden_patterns: list[str]


class FairHousingConfig(Contract):
    """Fair Housing compliance ruleset and protected classes."""

    source: str
    protected_classes: list[str]
    rules: list[FairHousingRule]


class TcpaRule(Contract):
    """Single TCPA SMS or lead-consent rule."""

    rule_id: str
    reference: str
    description: str
    required_phrases: list[str] = Field(default_factory=list)


class TcpaConfig(Contract):
    """TCPA SMS compliance ruleset and standardized opt-out keywords."""

    source: str
    opt_out_keywords: list[str]
    rules: list[TcpaRule]


class HumanReviewRule(Contract):
    """Pattern rule that routes unverifiable claims to human review."""

    rule_id: str
    reason: str
    patterns: list[str]


class HumanReviewPatternsConfig(Contract):
    """Collection of human-review trigger rules."""

    description: str
    rules: list[HumanReviewRule]


class ComplianceConfig(Contract):
    """Validated compliance configuration loaded from ``config/compliance.json``."""

    version: str
    disclaimer: str
    character_limits: CharacterLimits
    fair_housing: FairHousingConfig
    tcpa_sms: TcpaConfig
    human_review_patterns: HumanReviewPatternsConfig


class QuestionTopic(Contract):
    """Required qualification topic and matching keyword patterns for a vertical."""

    topic: str
    why: str
    keywords: list[str]


class VerticalConfig(Contract):
    """Vertical-specific campaign goal, trigger fields, brand name, and intake topics."""

    label: str
    goal: str
    trigger_fields: list[str]
    required_question_topics: list[QuestionTopic]
    brand_name: str


class VerticalsConfig(Contract):
    """Validated verticals configuration loaded from ``config/verticals.json``."""

    version: str
    verticals: dict[str, VerticalConfig]


def load_compliance_config(path: Path | None = None) -> ComplianceConfig:
    """Load and validate compliance guardrails from a JSON config file."""
    config_path = path if path is not None else DEFAULT_COMPLIANCE_CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return ComplianceConfig.model_validate(data)


def load_verticals_config(path: Path | None = None) -> VerticalsConfig:
    """Load and validate vertical definitions from a JSON config file."""
    config_path = path if path is not None else DEFAULT_VERTICALS_CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return VerticalsConfig.model_validate(data)


def _values_match(llm_value: float | int, source_value: float | int) -> bool:
    """Compare LLM numeric claim against source value with float tolerance or exact int check."""
    if isinstance(source_value, float) or isinstance(llm_value, float):
        return math.isclose(float(llm_value), float(source_value), abs_tol=NUMERIC_ABS_TOLERANCE)
    return int(llm_value) == int(source_value)


def verify_numeric_facts(
    facts: Sequence[NumericFact],
    county: CountyRecord,
) -> tuple[list[NumericFact], list[NumericCorrection]]:
    """Verify and reconcile LLM-cited numeric facts against an authoritative CountyRecord."""
    verified_facts: list[NumericFact] = []
    corrections: list[NumericCorrection] = []

    for fact in facts:
        source_val: object = (
            getattr(county, fact.field) if fact.field in CountyRecord.model_fields else None
        )
        if (
            source_val is None
            or isinstance(source_val, bool)
            or not isinstance(source_val, int | float)
        ):
            status: FactStatus = "unverified"
            corrections.append(
                NumericCorrection(
                    field=fact.field,
                    llm_value=fact.value,
                    source_value=None,
                    reason=f"Field '{fact.field}' not available in official county record.",
                )
            )
            verified_facts.append(fact.model_copy(update={"status": status}))
            continue

        if _values_match(fact.value, source_val):
            status = "verified"
            verified_facts.append(fact.model_copy(update={"status": status}))
        else:
            status = "corrected"
            corrections.append(
                NumericCorrection(
                    field=fact.field,
                    llm_value=fact.value,
                    source_value=source_val,
                    reason=f"Corrected from {fact.value} to source value {source_val}.",
                )
            )
            verified_facts.append(fact.model_copy(update={"value": source_val, "status": status}))

    return verified_facts, corrections


def check_character_limit(text: str, max_chars: int) -> tuple[bool, int]:
    """Return whether ``text`` fits within ``max_chars`` along with its character count."""
    length = len(text)
    return length <= max_chars, length


def find_fair_housing_violations(text: str, config: ComplianceConfig) -> list[str]:
    """Check text against Fair Housing forbidden patterns and return rule violation strings."""
    violations: list[str] = []
    for rule in config.fair_housing.rules:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule.forbidden_patterns):
            violations.append(f"{rule.rule_id}: {rule.description}")
    return violations


def validate_sms(text: str, brand_name: str, config: ComplianceConfig) -> list[str]:
    """Validate SMS copy for character limit, sender brand identification, and opt-out keyword."""
    errors: list[str] = []
    max_sms = config.character_limits.sms
    fits, length = check_character_limit(text, max_sms)
    if not fits:
        errors.append(f"SMS exceeds {max_sms} character limit ({length} chars).")

    if brand_name.lower() not in text.lower():
        errors.append(f"SMS must identify sender brand '{brand_name}'.")

    has_opt_out = any(
        re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE)
        for keyword in config.tcpa_sms.opt_out_keywords
    )
    if not has_opt_out:
        errors.append("SMS must include a TCPA opt-out keyword (e.g., STOP).")

    return errors


def validate_consent_disclosure(text: str, config: ComplianceConfig) -> list[str]:
    """Return required TCPA written-consent phrases missing from ``text``."""
    text_lower = text.lower()
    missing: list[str] = []
    for rule in config.tcpa_sms.rules:
        for phrase in rule.required_phrases:
            if phrase.lower() not in text_lower and phrase not in missing:
                missing.append(phrase)
    return missing


def detect_human_review_triggers(
    text: str,
    item_name: str,
    config: ComplianceConfig,
) -> list[HumanReviewItem]:
    """Detect unverifiable claims requiring human review, deduplicated by rule_id."""
    items: list[HumanReviewItem] = []
    seen_rule_ids: set[str] = set()
    for rule in config.human_review_patterns.rules:
        if rule.rule_id in seen_rule_ids:
            continue
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule.patterns):
            seen_rule_ids.add(rule.rule_id)
            items.append(HumanReviewItem(item=item_name, reason=rule.reason, rule_id=rule.rule_id))
    return items


def match_qualification_questions(
    questions: Sequence[str],
    vertical_config: VerticalConfig,
) -> tuple[list[QualificationQuestion], list[str]]:
    """Match qualification questions to vertical topics and return any missing required topics."""
    default_status: AssetStatus = "approved"
    qualification_questions: list[QualificationQuestion] = []
    matched_topics: set[str] = set()

    for idx, question_text in enumerate(questions, start=1):
        matching_topics = [
            topic
            for topic in vertical_config.required_question_topics
            if any(re.search(keyword, question_text, re.IGNORECASE) for keyword in topic.keywords)
        ]
        for topic in matching_topics:
            matched_topics.add(topic.topic)
        first_match = matching_topics[0] if matching_topics else None

        qualification_questions.append(
            QualificationQuestion(
                question_index=idx,
                question=question_text,
                topic=first_match.topic if first_match is not None else None,
                why=first_match.why if first_match is not None else None,
                status=default_status,
            )
        )

    missing_topics = [
        topic.topic
        for topic in vertical_config.required_question_topics
        if topic.topic not in matched_topics
    ]
    return qualification_questions, missing_topics
