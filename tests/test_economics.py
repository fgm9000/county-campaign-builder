"""Unit tests for deterministic auction unit-economics calculations."""

from __future__ import annotations

import pytest

from county_campaign_builder.economics import (
    build_economics_explanation,
    calculate_cpl,
    calculate_max_cpc,
    calculate_unit_economics,
    evaluate_traffic_light,
)
from county_campaign_builder.models import NumericRange


def test_calculate_cpl_normal_and_rounding() -> None:
    assert calculate_cpl(4.0, 0.08) == 50.0
    assert calculate_cpl(5.0, 0.03) == 166.67
    assert calculate_cpl(0.0, 0.10) == 0.0


@pytest.mark.parametrize("bad_cvr", [0.0, -0.05])
def test_calculate_cpl_rejects_non_positive_cvr(bad_cvr: float) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_cpl(3.0, bad_cvr)


def test_calculate_cpl_rejects_negative_cpc() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_cpl(-0.01, 0.05)


def test_calculate_max_cpc_normal_and_validation() -> None:
    assert calculate_max_cpc(85.0, 0.05) == 4.25
    assert calculate_max_cpc(120.0, 0.0633) == 7.6
    assert calculate_max_cpc(0.0, 0.05) == 0.0
    assert calculate_max_cpc(85.0, 0.0) == 0.0

    with pytest.raises(ValueError, match="Bid per lead cannot be negative"):
        calculate_max_cpc(-1.0, 0.05)

    with pytest.raises(ValueError, match="CVR cannot be negative"):
        calculate_max_cpc(85.0, -0.01)


def test_evaluate_traffic_light_all_verdicts_and_boundaries() -> None:
    assert evaluate_traffic_light(bid_per_lead=100.0, cpl_best=40.0, cpl_worst=80.0) == "green"
    assert evaluate_traffic_light(bid_per_lead=80.0, cpl_best=40.0, cpl_worst=80.0) == "green"

    assert evaluate_traffic_light(bid_per_lead=75.0, cpl_best=40.0, cpl_worst=80.0) == "yellow"
    assert evaluate_traffic_light(bid_per_lead=40.0, cpl_best=40.0, cpl_worst=80.0) == "yellow"

    assert evaluate_traffic_light(bid_per_lead=39.99, cpl_best=40.0, cpl_worst=80.0) == "red"


def test_build_economics_explanation_formats_all_verdicts() -> None:
    green = build_economics_explanation(
        verdict="green",
        bid_per_lead=120.0,
        cpl_best=30.0,
        cpl_worst=83.33,
        max_cpc=7.2,
        cpc_max=5.0,
        cvr_min=0.06,
    )
    assert green == (
        "Profitable across full range: worst-case CPL is $83.33, "
        "within $120.00 bid. Best-case CPL is $30.00."
    )

    yellow = build_economics_explanation(
        verdict="yellow",
        bid_per_lead=85.0,
        cpl_best=44.44,
        cpl_worst=140.0,
        max_cpc=4.25,
        cpc_max=7.0,
        cvr_min=0.05,
    )
    assert yellow == (
        "Profitable in favorable conditions: best-case CPL is $44.44 "
        "(under $85.00 bid), but worst-case CPL is $140.00. "
        "Max viable CPC at 5.0% CVR is $4.25."
    )

    red = build_economics_explanation(
        verdict="red",
        bid_per_lead=60.0,
        cpl_best=85.71,
        cpl_worst=225.0,
        max_cpc=2.4,
        cpc_max=9.0,
        cvr_min=0.04,
    )
    assert red == (
        "At $9.00 CPC and 4.0% CVR, lead costs $225.00; "
        "bid is $60.00: does not close. Best-case CPL is $85.71."
    )


def test_calculate_unit_economics_dallas_green_example() -> None:
    result = calculate_unit_economics(
        bid_per_lead_usd=120.0,
        cpc_usd=NumericRange(min=3.0, max=5.0),
        landing_cvr=NumericRange(min=0.06, max=0.10),
    )
    assert result.bid_per_lead_usd == 120.0
    assert result.cpl_best_usd == 30.0
    assert result.cpl_worst_usd == 83.33
    assert result.max_cpc_usd == 7.2
    assert result.verdict == "green"
    assert "Profitable across full range" in result.explanation


def test_calculate_unit_economics_pinellas_yellow_example() -> None:
    result = calculate_unit_economics(
        bid_per_lead_usd=85.0,
        cpc_usd=NumericRange(min=4.0, max=7.0),
        landing_cvr=NumericRange(min=0.05, max=0.09),
    )
    assert result.bid_per_lead_usd == 85.0
    assert result.cpl_best_usd == 44.44
    assert result.cpl_worst_usd == 140.0
    assert result.max_cpc_usd == 4.25
    assert result.verdict == "yellow"
    assert "Profitable in favorable conditions" in result.explanation


def test_calculate_unit_economics_cook_red_example() -> None:
    result = calculate_unit_economics(
        bid_per_lead_usd=60.0,
        cpc_usd=NumericRange(min=6.0, max=9.0),
        landing_cvr=NumericRange(min=0.04, max=0.07),
    )
    assert result.bid_per_lead_usd == 60.0
    assert result.cpl_best_usd == 85.71
    assert result.cpl_worst_usd == 225.0
    assert result.max_cpc_usd == 2.4
    assert result.verdict == "red"
    assert "does not close" in result.explanation
