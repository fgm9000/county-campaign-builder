"""Generate static demo fixtures in web/examples.json from the offline pipeline.

Runs the three canonical demo counties (Dallas, Pinellas, Cook) with
``Settings(fake_model=True)`` and serializes the deterministic campaign outputs
and cross-county comparison for the static web playground.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from county_campaign_builder.graph import (
    _summarize_campaign,
    create_default_dependencies,
    run_campaign,
)
from county_campaign_builder.llm import COOK_FIPS, DALLAS_FIPS, PINELLAS_FIPS
from county_campaign_builder.models import (
    CampaignComparison,
    CampaignInput,
    CountyCampaign,
    NumericRange,
)
from county_campaign_builder.settings import Settings

EXAMPLES_VERSION = "1.0"
WEB_DIR = REPO_ROOT / "web"
EXAMPLES_PATH = WEB_DIR / "examples.json"

CANONICAL_INPUTS: tuple[CampaignInput, ...] = (
    CampaignInput(
        county_fips=DALLAS_FIPS,
        vertical="motivated_seller",
        bid_per_lead_usd=125.0,
        cpc_usd=NumericRange(min=2.0, max=4.0),
        landing_cvr=NumericRange(min=0.05, max=0.10),
    ),
    CampaignInput(
        county_fips=PINELLAS_FIPS,
        vertical="motivated_seller",
        bid_per_lead_usd=125.0,
        cpc_usd=NumericRange(min=4.5, max=9.0),
        landing_cvr=NumericRange(min=0.06, max=0.10),
    ),
    CampaignInput(
        county_fips=COOK_FIPS,
        vertical="motivated_seller",
        bid_per_lead_usd=125.0,
        cpc_usd=NumericRange(min=11.0, max=15.0),
        landing_cvr=NumericRange(min=0.05, max=0.08),
    ),
)


def build_examples_payload(generated_at: str | None = None) -> dict[str, Any]:
    """Run the 3 canonical counties in fake mode and assemble the examples.json payload."""
    deps = create_default_dependencies(Settings(fake_model=True))
    campaigns: list[CountyCampaign] = [run_campaign(item, deps) for item in CANONICAL_INPUTS]

    summaries = [_summarize_campaign(campaign) for campaign in campaigns]
    comp_output = deps.model.compare_counties(summaries)
    recommended = comp_output.recommended_county_fips.strip() or None
    comparison = CampaignComparison(
        campaigns=campaigns,
        recommended_county_fips=recommended,
        summary=comp_output.summary,
    )

    resolved_date = (
        generated_at if generated_at is not None else datetime.now(UTC).date().isoformat()
    )

    return {
        "version": EXAMPLES_VERSION,
        "generated_at": resolved_date,
        "canonical_inputs": {
            item.county_fips: {
                "county_fips": item.county_fips,
                "vertical": item.vertical,
                "bid_per_lead_usd": item.bid_per_lead_usd,
                "cpc_usd": item.cpc_usd.model_dump(mode="json"),
                "landing_cvr": item.landing_cvr.model_dump(mode="json"),
            }
            for item in CANONICAL_INPUTS
        },
        "comparison": comparison.model_dump(mode="json"),
        "campaigns": [campaign.model_dump(mode="json") for campaign in campaigns],
    }


def write_examples(output_path: Path = EXAMPLES_PATH) -> Path:
    """Serialize the canonical examples payload to ``output_path`` with 2-space indent."""
    payload = build_examples_payload()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    """Generate ``web/examples.json``."""
    written = write_examples()
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
