"""Deterministic auction unit-economics calculations for county campaigns."""

from __future__ import annotations

from county_campaign_builder.models import NumericRange, TrafficLight, UnitEconomics


def calculate_cpl(cpc: float, cvr: float) -> float:
    """Calculate cost per lead (CPL) from cost per click and conversion rate."""
    if cvr <= 0:
        raise ValueError("Landing conversion rate (CVR) must be greater than zero.")
    if cpc < 0:
        raise ValueError("Cost per click (CPC) cannot be negative.")
    return round(cpc / cvr, 2)


def calculate_max_cpc(bid_per_lead: float, cvr: float) -> float:
    """Calculate the maximum break-even CPC for a given lead bid and CVR."""
    if bid_per_lead < 0:
        raise ValueError("Bid per lead cannot be negative.")
    if cvr < 0:
        raise ValueError("CVR cannot be negative.")
    return round(bid_per_lead * cvr, 2)


def evaluate_traffic_light(
    bid_per_lead: float,
    cpl_best: float,
    cpl_worst: float,
) -> TrafficLight:
    """Classify campaign unit economics into green, yellow, or red against lead bid."""
    if cpl_worst <= bid_per_lead:
        return "green"
    if cpl_best <= bid_per_lead:
        return "yellow"
    return "red"


def build_economics_explanation(
    verdict: TrafficLight,
    bid_per_lead: float,
    cpl_best: float,
    cpl_worst: float,
    max_cpc: float,
    cpc_max: float,
    cvr_min: float,
) -> str:
    """Build a concise, business-friendly summary of the unit-economics verdict."""
    if verdict == "red":
        return (
            f"At ${cpc_max:.2f} CPC and {cvr_min * 100:.1f}% CVR, lead costs ${cpl_worst:.2f}; "
            f"bid is ${bid_per_lead:.2f}: does not close. Best-case CPL is ${cpl_best:.2f}."
        )
    if verdict == "yellow":
        return (
            f"Profitable in favorable conditions: best-case CPL is ${cpl_best:.2f} "
            f"(under ${bid_per_lead:.2f} bid), but worst-case CPL is ${cpl_worst:.2f}. "
            f"Max viable CPC at {cvr_min * 100:.1f}% CVR is ${max_cpc:.2f}."
        )
    return (
        f"Profitable across full range: worst-case CPL is ${cpl_worst:.2f}, "
        f"within ${bid_per_lead:.2f} bid. Best-case CPL is ${cpl_best:.2f}."
    )


def calculate_unit_economics(
    bid_per_lead_usd: float,
    cpc_usd: NumericRange,
    landing_cvr: NumericRange,
) -> UnitEconomics:
    """Compute best/worst-case CPL, max viable CPC, traffic-light verdict, and explanation."""
    cpl_best_usd = calculate_cpl(cpc_usd.min, landing_cvr.max)
    cpl_worst_usd = calculate_cpl(cpc_usd.max, landing_cvr.min)
    max_cpc_usd = calculate_max_cpc(bid_per_lead_usd, landing_cvr.min)
    verdict = evaluate_traffic_light(bid_per_lead_usd, cpl_best_usd, cpl_worst_usd)
    explanation = build_economics_explanation(
        verdict=verdict,
        bid_per_lead=bid_per_lead_usd,
        cpl_best=cpl_best_usd,
        cpl_worst=cpl_worst_usd,
        max_cpc=max_cpc_usd,
        cpc_max=cpc_usd.max,
        cvr_min=landing_cvr.min,
    )
    return UnitEconomics(
        bid_per_lead_usd=bid_per_lead_usd,
        cpl_best_usd=cpl_best_usd,
        cpl_worst_usd=cpl_worst_usd,
        max_cpc_usd=max_cpc_usd,
        verdict=verdict,
        explanation=explanation,
    )
