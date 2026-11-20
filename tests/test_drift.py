"""Drift tests ensuring web/examples.json stays synced with the offline pipeline."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast

from county_campaign_builder.llm import COOK_FIPS, DALLAS_FIPS, PINELLAS_FIPS
from county_campaign_builder.models import CampaignComparison, CountyCampaign

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = REPO_ROOT / "web" / "examples.json"
BUILD_EXAMPLES_PATH = REPO_ROOT / "scripts" / "build_examples.py"


def _load_examples_json() -> dict[str, Any]:
    raw_text = EXAMPLES_PATH.read_text(encoding="utf-8")
    parsed: object = json.loads(raw_text)
    assert isinstance(parsed, dict)
    return parsed


def _load_build_examples_payload() -> Callable[[str | None], dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("build_examples_script", BUILD_EXAMPLES_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn: object = module.build_examples_payload
    assert callable(fn)
    return cast("Callable[[str | None], dict[str, Any]]", fn)


def test_examples_json_exists_and_is_valid_json() -> None:
    assert EXAMPLES_PATH.is_file(), f"Missing generated examples fixture: {EXAMPLES_PATH}"
    data = _load_examples_json()

    assert data.get("version") == "1.0"
    generated_at = data.get("generated_at")
    assert isinstance(generated_at, str)
    date.fromisoformat(generated_at)

    assert set(data.keys()) == {
        "version",
        "generated_at",
        "canonical_inputs",
        "comparison",
        "campaigns",
    }
    CampaignComparison.model_validate(data["comparison"])


def test_examples_contains_canonical_counties_and_verdicts() -> None:
    data = _load_examples_json()
    canonical_inputs = data["canonical_inputs"]
    assert isinstance(canonical_inputs, dict)
    assert list(canonical_inputs.keys()) == [DALLAS_FIPS, PINELLAS_FIPS, COOK_FIPS]

    campaigns_raw = data["campaigns"]
    assert isinstance(campaigns_raw, list)
    campaigns = [CountyCampaign.model_validate(item) for item in campaigns_raw]
    assert [c.county_fips for c in campaigns] == [DALLAS_FIPS, PINELLAS_FIPS, COOK_FIPS]

    verdicts = {c.county_fips: c.unit_economics.verdict for c in campaigns}
    assert verdicts == {
        DALLAS_FIPS: "green",
        PINELLAS_FIPS: "yellow",
        COOK_FIPS: "red",
    }

    comparison = CampaignComparison.model_validate(data["comparison"])
    assert comparison.recommended_county_fips == DALLAS_FIPS


def test_examples_dallas_has_numeric_correction_trap() -> None:
    data = _load_examples_json()
    campaigns_raw = data["campaigns"]
    assert isinstance(campaigns_raw, list)
    campaigns = [CountyCampaign.model_validate(item) for item in campaigns_raw]
    dallas = next(c for c in campaigns if c.county_fips == DALLAS_FIPS)

    assert dallas.status == "success"
    hail_corrections = [corr for corr in dallas.corrections if corr.field == "hail_reports_1in"]
    assert len(hail_corrections) == 1
    assert hail_corrections[0].llm_value == 120
    assert hail_corrections[0].source_value == 102

    hail_facts = [fact for fact in dallas.facts if fact.field == "hail_reports_1in"]
    assert len(hail_facts) == 1
    assert hail_facts[0].status == "corrected"
    assert hail_facts[0].value == 102


def test_examples_json_matches_regenerated_payload_with_zero_drift() -> None:
    disk_raw = EXAMPLES_PATH.read_text(encoding="utf-8")
    disk_data: object = json.loads(disk_raw)
    assert isinstance(disk_data, dict)

    disk_generated_at = disk_data.get("generated_at")
    assert isinstance(disk_generated_at, str)

    build_examples_payload = _load_build_examples_payload()
    regenerated = build_examples_payload(disk_generated_at)
    assert disk_data == regenerated
    assert disk_raw == json.dumps(regenerated, indent=2) + "\n"
