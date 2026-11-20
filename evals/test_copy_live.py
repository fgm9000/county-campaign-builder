"""Live copy-quality evals (real Anthropic models, G-Eval judge). Collected only with LIVE_EVAL=1.

Run with:
    LIVE_EVAL=1 uv run pytest evals/test_copy_live.py -q
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from deepeval.evaluate import assert_test
from deepeval.metrics import BaseMetric, GEval
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from county_campaign_builder.county_data import load_county_table
from county_campaign_builder.domain import load_compliance_config, load_verticals_config
from county_campaign_builder.graph import CampaignDependencies, run_campaign
from county_campaign_builder.llm import COOK_FIPS, DALLAS_FIPS, PINELLAS_FIPS, AnthropicModelClient
from county_campaign_builder.models import CampaignInput, NumericRange
from evals.metrics import deterministic_metrics, to_test_case

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "eval-results-live.json"
JUDGE_MODEL = "claude-opus-5-5"
GEVAL_THRESHOLD = 0.7

COPY_QUALITY_STEPS = [
    (
        "Check local relevance: headlines, descriptions, landing page copy, SMS, and emails "
        "reference the target county or grounded county facts rather than generic national filler."
    ),
    (
        "Check proposition clarity: the offer is explicit and tailored to the vertical "
        "(straightforward as-is cash offer without repairs/listing for motivated_seller, or "
        "storm-ready roof inspection/replacement for roofing)."
    ),
    (
        "Check lack of generic cliches: the copy avoids empty hype, vague filler slogans, and "
        "ungrounded promises."
    ),
    ("Check overall tone and readability: concise, natural, and credible for local US homeowners."),
]


@dataclass(frozen=True)
class LiveEvalCase:
    """Live evaluation scenario combining county, vertical, and auction inputs."""

    case_id: str
    input_data: CampaignInput


LIVE_CASES: tuple[LiveEvalCase, ...] = (
    LiveEvalCase(
        case_id="dallas_motivated_seller",
        input_data=CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        ),
    ),
    LiveEvalCase(
        case_id="pinellas_motivated_seller",
        input_data=CampaignInput(
            county_fips=PINELLAS_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=4.5, max=9.0),
            landing_cvr=NumericRange(min=0.06, max=0.10),
        ),
    ),
    LiveEvalCase(
        case_id="cook_motivated_seller",
        input_data=CampaignInput(
            county_fips=COOK_FIPS,
            vertical="motivated_seller",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=11.0, max=15.0),
            landing_cvr=NumericRange(min=0.05, max=0.08),
        ),
    ),
    LiveEvalCase(
        case_id="dallas_roofing",
        input_data=CampaignInput(
            county_fips=DALLAS_FIPS,
            vertical="roofing",
            bid_per_lead_usd=125.0,
            cpc_usd=NumericRange(min=2.0, max=4.0),
            landing_cvr=NumericRange(min=0.05, max=0.10),
        ),
    ),
)


@dataclass
class LiveReport:
    """Collects per-case live evaluation scores and writes JSON summary on teardown."""

    cases: list[dict[str, object]] = field(default_factory=list)

    def write(self) -> None:
        summary = {
            "judge_model": JUDGE_MODEL,
            "geval_threshold": GEVAL_THRESHOLD,
            "cases": self.cases,
        }
        REPORT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def live_deps() -> CampaignDependencies:
    return CampaignDependencies(
        model=AnthropicModelClient(),
        county_table=load_county_table(PROJECT_ROOT / "data" / "counties.parquet"),
        compliance_config=load_compliance_config(PROJECT_ROOT / "config" / "compliance.json"),
        verticals_config=load_verticals_config(PROJECT_ROOT / "config" / "verticals.json"),
    )


@pytest.fixture(scope="module")
def report() -> Iterator[LiveReport]:
    live_report = LiveReport()
    yield live_report
    live_report.write()


def _copy_geval() -> GEval:
    return GEval(
        name="Campaign copy quality",
        evaluation_steps=COPY_QUALITY_STEPS,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=GEVAL_THRESHOLD,
        async_mode=False,
    )


def _report_row(case_id: str, metrics: list[BaseMetric]) -> dict[str, object]:
    return {
        "case_id": case_id,
        "metrics": [
            {
                "name": metric.__name__,
                "score": metric.score,
                "success": metric.success,
                "reason": metric.reason,
            }
            for metric in metrics
        ],
    }


@pytest.mark.parametrize("case", LIVE_CASES, ids=lambda case: case.case_id)
def test_live_copy_quality_and_deterministic_guardrails(
    case: LiveEvalCase,
    live_deps: CampaignDependencies,
    report: LiveReport,
) -> None:
    campaign = run_campaign(case.input_data, live_deps)
    assert campaign.status == "success"

    geval = _copy_geval()
    judges: list[BaseMetric] = [geval]
    det_metrics = deterministic_metrics(case.input_data, live_deps)
    copy_test_case = LLMTestCase(
        input=(
            f"County: {campaign.county_name} ({campaign.county_fips}), "
            f"Vertical: {campaign.vertical}"
        ),
        actual_output=campaign.assets.model_dump_json(),
    )

    try:
        assert_test(copy_test_case, judges, run_async=False)
        assert_test(to_test_case(case.input_data, campaign), det_metrics, run_async=False)
    finally:
        report.cases.append(_report_row(case.case_id, [geval, *det_metrics]))
