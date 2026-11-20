"""Deterministic, reusable prompt builders for the county-level campaign pipeline."""

from __future__ import annotations

from collections.abc import Sequence

from county_campaign_builder.county_data import COUNT_COLUMNS, CountyRecord
from county_campaign_builder.domain import VerticalConfig
from county_campaign_builder.models import NumericFact

CENSUS_SOURCE = "U.S. Census Bureau ACS 2020-2024"
NOAA_SOURCE = "NOAA Storm Events 2020-2024"

AD_HEADLINE_MAX_CHARS = 30
AD_DESCRIPTION_MAX_CHARS = 90
SMS_MAX_CHARS = 160


def _source_for_field(field: str) -> str:
    """Return the authoritative dataset label for a CountyRecord field."""
    if field in COUNT_COLUMNS:
        return NOAA_SOURCE
    return CENSUS_SOURCE


def _format_county_trigger_fields(county: CountyRecord, trigger_fields: Sequence[str]) -> str:
    """Format the vertical's trigger fields from a CountyRecord with exact values and sources."""
    lines: list[str] = []
    for field in trigger_fields:
        value: object = getattr(county, field, None)
        source = _source_for_field(field)
        if value is None:
            lines.append(f"- {field}: N/A (withheld by source) [source: {source}]")
        else:
            lines.append(f"- {field}: {value} [source: {source}]")
    return "\n".join(lines) if lines else "- None configured."


def _format_verified_facts(verified_facts: Sequence[NumericFact]) -> str:
    """Format verified numeric county facts for downstream copy prompts."""
    if not verified_facts:
        return "- None provided. Do not invent or assume any county statistics."
    lines: list[str] = []
    for fact in verified_facts:
        lines.append(
            f"- {fact.claim} (field: {fact.field}, value: {fact.value}, source: {fact.source})"
        )
    return "\n".join(lines)


def build_trigger_interpretation_prompt(
    county: CountyRecord,
    vertical_config: VerticalConfig,
) -> str:
    """Build the Haiku prompt to interpret county data fields into 3 to 5 grounded triggers."""
    fields_block = _format_county_trigger_fields(county, vertical_config.trigger_fields)
    return (
        "You are a US local market analyst for real estate and home services lead generation.\n\n"
        f"County: {county.county_name} (FIPS: {county.fips}, "
        f"Storm window: {county.years_covered})\n"
        f"Vertical: {vertical_config.label}\n"
        f"Campaign Goal: {vertical_config.goal}\n\n"
        "Authoritative County Record Fields (use ONLY these values):\n"
        f"{fields_block}\n\n"
        "Task:\n"
        "Interpret the county data fields above into 3 to 5 concrete messaging triggers that\n"
        "explain why homeowners in this county are strong prospects for this vertical.\n\n"
        "Structured Output Requirements:\n"
        "Return 3 to 5 trigger items. Every item MUST include:\n"
        "- claim: concise natural-language statement linking the datum to homeowner motivation.\n"
        "- field: exact column name from the Authoritative County Record Fields list above.\n"
        "- value: exact numeric value (int or float) matching the county record above.\n"
        f'- source: exact source string, either "{CENSUS_SOURCE}" or "{NOAA_SOURCE}".\n\n'
        "Strict Grounding Rules:\n"
        "- NEVER invent, estimate, round differently, or extrapolate numbers.\n"
        "- Every claim and numeric value MUST match the county record above verbatim.\n"
        "- Do NOT cite any field marked N/A (withheld by source).\n"
        "- Use only the exact field names listed above."
    )


def build_qualification_prompt(
    county_name: str,
    vertical_config: VerticalConfig,
    verified_facts: Sequence[NumericFact],
) -> str:
    """Build the Haiku prompt to generate 5 vertical-aligned lead-qualification questions."""
    topics_lines = [
        f"{idx}. Topic: {item.topic}\n   Why this matters: {item.why}"
        for idx, item in enumerate(vertical_config.required_question_topics, start=1)
    ]
    topics_block = "\n".join(topics_lines) if topics_lines else "- No topics configured."
    facts_block = _format_verified_facts(verified_facts)

    return (
        "You are a US lead-qualification strategist for real estate and home services.\n\n"
        f"Target County: {county_name}\n"
        f"Vertical: {vertical_config.label}\n"
        f"Brand: {vertical_config.brand_name}\n"
        f"Campaign Goal: {vertical_config.goal}\n\n"
        "Verified Local Facts (use only these if referencing local context):\n"
        f"{facts_block}\n\n"
        "Required Qualification Topics (and why each topic is vital):\n"
        f"{topics_block}\n\n"
        "Task:\n"
        "Write exactly 5 lead-qualification intake questions tailored to homeowners in\n"
        f"{county_name}, covering every required topic listed above (one primary question\n"
        "per topic).\n\n"
        "Structured Output Requirements:\n"
        "For each of the 5 questions, return:\n"
        "- question_index: integer 1 through 5.\n"
        "- topic: exact topic name from the Required Qualification Topics list.\n"
        "- question: clear, polite, direct intake question written in natural US English.\n"
        "- why: brief explanation of why this topic is vital for lead qualification.\n\n"
        "Rules:\n"
        "- Cover all required topics with clear, unambiguous wording.\n"
        "- Do NOT invent or extrapolate county statistics.\n"
        "- Keep all questions respectful and Fair Housing compliant."
    )


def build_ads_and_lp_prompt(
    county_name: str,
    vertical_config: VerticalConfig,
    verified_facts: Sequence[NumericFact],
) -> str:
    """Build the Sonnet prompt to draft Google Ads copy and above-the-fold landing page copy."""
    facts_block = _format_verified_facts(verified_facts)
    return (
        "You are a senior US performance copywriter and compliance-aware marketer for\n"
        "real estate and home services.\n\n"
        f"Target County: {county_name}\n"
        f"Brand Name: {vertical_config.brand_name}\n"
        f"Vertical: {vertical_config.label}\n"
        f"Campaign Goal: {vertical_config.goal}\n\n"
        "Verified Local Facts (cite ONLY numbers from this list):\n"
        f"{facts_block}\n\n"
        "Task:\n"
        "Draft the Google Responsive Search Ad copy and the above-the-fold landing page\n"
        f"copy for {county_name}.\n\n"
        "Structured Output Requirements:\n"
        "1. Ad Copy:\n"
        f"   - headlines: 3 headlines, STRICT limit <= {AD_HEADLINE_MAX_CHARS} characters each\n"
        "     (including spaces and punctuation).\n"
        f"   - descriptions: 2 descriptions, STRICT limit <= {AD_DESCRIPTION_MAX_CHARS} "
        "characters\n"
        "     each (including spaces and punctuation).\n"
        "2. Landing Page Top:\n"
        "   - headline: clear, locally relevant primary headline.\n"
        "   - subheadline: concise supporting statement.\n"
        "   - cta_text: action-oriented call-to-action button text.\n"
        "   - bullet_points: 3 to 4 homeowner benefit bullet points (as-is purchase, zero\n"
        "     commissions, flexible closing, local specialist). Do NOT paste raw census or\n"
        "     demographic percentages here; keep bullets homeowner-facing.\n"
        "   - consent_disclosure: TCPA written-consent statement placed by the form that\n"
        '     MUST include all three required phrases (case-insensitive): "automated",\n'
        '     "not a condition", and "stop" (for example: consent to receive automated\n'
        "     calls/texts, consent is not a condition of purchase, reply STOP to opt out).\n\n"
        "Mandatory Fair Housing & Compliance Rules:\n"
        "- Fair Housing (42 U.S.C. 3604(c) and (e)): NEVER use discriminatory language or\n"
        "  state preferences or limitations based on race, color, religion, sex, disability,\n"
        "  familial status, or national origin.\n"
        '- NO familial status limits (e.g., never say "adults only", "no kids",\n'
        '  "without children", "perfect for singles", or "not suitable for families").\n'
        '- NO blockbusting language (e.g., never say "neighborhood is changing",\n'
        '  "sell before values decline", or "new residents are moving in").\n'
        "- Ground all local claims in the Verified Local Facts above; NEVER invent numbers.\n"
        "- Avoid unverifiable promises (e.g., guaranteed outcomes, free roof, or fixed\n"
        "  closing-day guarantees)."
    )


def build_followup_prompt(
    county_name: str,
    brand_name: str,
    verified_facts: Sequence[NumericFact],
) -> str:
    """Build the Haiku prompt to draft 2 TCPA-compliant SMS messages and 2 follow-up emails."""
    facts_block = _format_verified_facts(verified_facts)
    return (
        "You are a US lifecycle copywriter for real estate acquisitions.\n"
        "Your audience is motivated homeowners seeking a direct as-is cash sale.\n\n"
        f"Target County: {county_name}\n"
        f"Brand Name: {brand_name}\n\n"
        "Audience Context:\n"
        "The homeowner wants to sell directly to avoid repairs, agent fees, or closing delays.\n"
        "Draft helpful, respectful follow-up copy focused entirely on their timeline and needs.\n"
        "Do NOT cite macro census or weather statistics in seller communications.\n\n"
        "Verified Local Facts (for internal market reference):\n"
        f"{facts_block}\n\n"
        "Task:\n"
        f"Write 2 SMS follow-up messages and 2 email follow-ups for leads in {county_name}.\n\n"
        "Structured Output Requirements:\n"
        "1. sms_messages (exactly 2 items, message_index 1 and 2):\n"
        f"   - STRICT limit: <= {SMS_MAX_CHARS} characters per SMS (including spaces,\n"
        "     punctuation, brand name, and opt-out text).\n"
        f'   - Each SMS MUST include the exact brand name "{brand_name}".\n'
        '   - Each SMS MUST include a clear opt-out instruction (e.g., "Reply STOP to opt out").\n'
        "2. email_followups (exactly 2 items, email_index 1 and 2):\n"
        "   - Each email MUST include a subject line and clear, helpful body text.\n\n"
        "Compliance & Grounding Rules:\n"
        "- Follow Fair Housing rules: no discriminatory preferences, familial status limits,\n"
        "  or blockbusting language.\n"
        "- Avoid unverifiable guarantees or promises."
    )


def build_regeneration_prompt(
    county_name: str,
    brand_name: str,
    failed_items: Sequence[tuple[str, str]],
    vertical_config: VerticalConfig,
) -> str:
    """Build a targeted prompt to rewrite only specific failed campaign assets."""
    if failed_items:
        failed_block = "\n".join(
            f"{idx}. Item: {item_id}\n   Current invalid text / rejection reason: {details}"
            for idx, (item_id, details) in enumerate(failed_items, start=1)
        )
    else:
        failed_block = "- No failed items provided."

    return (
        "You are a US campaign compliance editor rewriting ONLY rejected campaign assets.\n\n"
        f"Target County: {county_name}\n"
        f"Brand Name: {brand_name}\n"
        f"Vertical: {vertical_config.label}\n"
        f"Campaign Goal: {vertical_config.goal}\n\n"
        "Failed Assets to Rewrite:\n"
        f"{failed_block}\n\n"
        "Task:\n"
        "Rewrite ONLY the specific failed items listed above so every item passes validation.\n"
        "Do NOT modify or regenerate any assets that are not listed above.\n"
        "For each failed item, inspect its identifier, current invalid text (or summary),\n"
        "and exact rejection reason, then return a compliant replacement.\n\n"
        "Compliance Constraints (apply all rules relevant to each failed item):\n"
        f"- Ad headlines: STRICT <= {AD_HEADLINE_MAX_CHARS} characters.\n"
        f"- Ad descriptions: STRICT <= {AD_DESCRIPTION_MAX_CHARS} characters.\n"
        f"- SMS messages: STRICT <= {SMS_MAX_CHARS} characters, MUST contain exact brand\n"
        f'  name "{brand_name}", and MUST include an opt-out keyword\n'
        '  (e.g., "Reply STOP to opt out").\n'
        '- Landing page consent_disclosure: MUST include "automated", "not a condition",\n'
        '  and "stop" (case-insensitive).\n'
        "- Fair Housing: NO discriminatory language, NO familial status limits, and NO\n"
        '  blockbusting ("neighborhood is changing", etc.).\n'
        "- Grounding: NEVER invent numbers or make unverifiable guarantees."
    )


def build_comparison_prompt(campaign_summaries: Sequence[str]) -> str:
    """Build the prompt for an executive comparison and county launch recommendation."""
    if campaign_summaries:
        summaries_block = "\n\n".join(
            f"County Summary {idx}:\n{summary}"
            for idx, summary in enumerate(campaign_summaries, start=1)
        )
    else:
        summaries_block = "No county campaign summaries provided."

    return (
        "You are a US performance marketing director evaluating county-level campaigns.\n\n"
        "County Campaign Summaries:\n"
        f"{summaries_block}\n\n"
        "Task:\n"
        "Write a concise executive summary comparing these counties and recommending which\n"
        "county should be prioritized for campaign launch.\n\n"
        "Your comparison MUST address:\n"
        "1. Unit Economics (Traffic Light): compare green, yellow, and red verdicts,\n"
        "   best-case vs. worst-case CPL relative to lead bid, and max viable CPC.\n"
        "2. Market Triggers: compare the strength and relevance of verified local triggers\n"
        "   from Census ACS and NOAA storm records.\n"
        "3. Launch Recommendation: identify the top-priority county (name and FIPS if\n"
        "   available), explain the rationale, and note any economic or compliance caveats\n"
        "   (especially if top candidates are yellow or red).\n\n"
        "Rules:\n"
        "- Base your analysis strictly on the summaries above.\n"
        "- NEVER invent numbers, alter traffic-light verdicts, or extrapolate metrics."
    )
