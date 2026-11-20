"""Pydantic v2 data contracts for the county-level campaign builder."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

TrafficLight = Literal["green", "yellow", "red"]
Vertical = Literal["motivated_seller", "roofing"]
AssetStatus = Literal["approved", "rejected", "regenerated", "needs_human_review", "missing"]
FactStatus = Literal["verified", "corrected", "unverified"]
CampaignStatus = Literal["success", "failed"]

FIPS_PATTERN = r"^\d{5}$"
MAX_COUNTIES_PER_COMPARISON = 10


def normalize_nfc(value: str) -> str:
    """Normalize text to Unicode NFC and strip surrounding whitespace."""
    return unicodedata.normalize("NFC", value).strip()


CleanText = Annotated[str, AfterValidator(normalize_nfc)]
CountyFips = Annotated[str, Field(min_length=5, max_length=5, pattern=FIPS_PATTERN)]


class Contract(BaseModel):
    """Base contract for all county-campaign-builder models: immutable once constructed."""

    model_config = ConfigDict(frozen=True)


class NumericRange(Contract):
    """Closed non-negative numeric interval with ``min <= max``."""

    min: float = Field(ge=0)
    max: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> Self:
        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")
        return self


class _CampaignInputBase(Contract):
    """Shared economic and vertical inputs for single- and multi-county requests."""

    vertical: Vertical
    bid_per_lead_usd: float = Field(gt=0)
    cpc_usd: NumericRange
    landing_cvr: NumericRange

    @model_validator(mode="after")
    def _validate_landing_cvr(self) -> Self:
        if self.landing_cvr.max > 1.0:
            raise ValueError("landing_cvr values must be between 0 and 1 (max <= 1.0)")
        return self


class CampaignInput(_CampaignInputBase):
    """Input parameters for building a single-county lead-generation campaign."""

    county_fips: CountyFips


class MultiCountyInput(_CampaignInputBase):
    """Input parameters for comparing campaigns across up to 10 counties."""

    county_fips_list: list[CountyFips] = Field(min_length=1, max_length=MAX_COUNTIES_PER_COMPARISON)

    @model_validator(mode="after")
    def _reject_duplicate_fips(self) -> Self:
        if len(set(self.county_fips_list)) != len(self.county_fips_list):
            raise ValueError("county_fips_list must not contain duplicate FIPS codes")
        return self


class NumericFact(Contract):
    """Grounded numeric claim backed by county Census or NOAA source data."""

    claim: CleanText
    field: CleanText
    value: float | int
    source: CleanText
    status: FactStatus = "unverified"


class NumericCorrection(Contract):
    """Record of an LLM-produced numeric value reconciled against authoritative county data."""

    field: CleanText
    llm_value: float | int
    source_value: float | int | None
    reason: CleanText


class UnitEconomics(Contract):
    """Deterministic unit-economics calculation and traffic-light verdict for a campaign."""

    bid_per_lead_usd: float
    cpl_best_usd: float
    cpl_worst_usd: float
    max_cpc_usd: float
    verdict: TrafficLight
    explanation: CleanText


class _AssetContract(Contract):
    """Shared moderation status fields for generated campaign assets."""

    status: AssetStatus = "approved"
    rejection_reason: CleanText | None = None


class _AdTextAsset(_AssetContract):
    """Shared text payload for short-form Google Ads copy assets."""

    text: CleanText


class AdHeadline(_AdTextAsset):
    """Single responsive search ad headline."""


class AdDescription(_AdTextAsset):
    """Single responsive search ad description."""


class AdCopy(Contract):
    """Collection of headlines and descriptions for a search ad."""

    headlines: list[AdHeadline] = Field(default_factory=list)
    descriptions: list[AdDescription] = Field(default_factory=list)


class LandingPageTop(_AssetContract):
    """Above-the-fold landing page copy and lead-capture consent disclosure."""

    headline: CleanText
    subheadline: CleanText
    cta_text: CleanText
    bullet_points: list[CleanText] = Field(default_factory=list)
    consent_disclosure: CleanText


class SMSMessage(_AssetContract):
    """Single follow-up SMS message with tracked character count."""

    message_index: int
    text: CleanText
    char_count: int


class EmailFollowup(_AssetContract):
    """Single follow-up email asset."""

    email_index: int
    subject: CleanText
    body: CleanText


class QualificationQuestion(_AssetContract):
    """Lead-qualification question used during intake."""

    question_index: int
    question: CleanText
    topic: CleanText | None = None
    why: CleanText | None = None


class CampaignAssets(Contract):
    """Complete bundle of generated assets for one county campaign."""

    questions: list[QualificationQuestion] = Field(default_factory=list)
    ad_copy: AdCopy = Field(default_factory=AdCopy)
    landing_page: LandingPageTop | None = None
    sms_messages: list[SMSMessage] = Field(default_factory=list)
    email_followups: list[EmailFollowup] = Field(default_factory=list)


class HumanReviewItem(Contract):
    """Flagged asset or claim requiring human sign-off under a compliance rule."""

    item: CleanText
    reason: CleanText
    rule_id: CleanText


class CountyCampaign(Contract):
    """Full output package for a single county campaign."""

    county_fips: CleanText
    county_name: CleanText
    vertical: Vertical
    status: CampaignStatus = "success"
    error_message: CleanText | None = None
    facts: list[NumericFact] = Field(default_factory=list)
    corrections: list[NumericCorrection] = Field(default_factory=list)
    unit_economics: UnitEconomics
    assets: CampaignAssets = Field(default_factory=CampaignAssets)
    needs_human_review: list[HumanReviewItem] = Field(default_factory=list)


class CampaignComparison(Contract):
    """Side-by-side comparison across multiple county campaigns."""

    campaigns: list[CountyCampaign] = Field(default_factory=list)
    recommended_county_fips: CleanText | None = None
    summary: CleanText = ""
