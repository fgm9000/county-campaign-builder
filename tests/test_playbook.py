"""Tests for the non-code operations playbook and auction-math spreadsheet."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import openpyxl

from county_campaign_builder.county_data import load_county_table
from county_campaign_builder.domain import load_compliance_config, load_verticals_config
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

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_DIR = REPO_ROOT / "playbook"
WORKBOOK_PATH = PLAYBOOK_DIR / "auction-math.xlsx"
README_PATH = PLAYBOOK_DIR / "README.md"
BUILD_PLAYBOOK_PATH = REPO_ROOT / "scripts" / "build_playbook.py"


def _load_build_playbook_module() -> ModuleType:
    module_name = "build_playbook_script"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, BUILD_PLAYBOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_mod = _load_build_playbook_module()
COUNTIES_PARQUET_PATH: Path = cast(Path, _mod.COUNTIES_PARQUET_PATH)
DEMO_COUNTIES: list[Any] = cast("list[Any]", _mod.DEMO_COUNTIES)
SUMMARY_HEADERS: tuple[str, ...] = cast("tuple[str, ...]", _mod.SUMMARY_HEADERS)
_build_sample_verified_facts: Any = _mod._build_sample_verified_facts
_format_county_summary_line: Any = _mod._format_county_summary_line
build_playbook_markdown: Any = _mod.build_playbook_markdown
build_workbook: Any = _mod.build_workbook


def _load_workbook() -> Any:
    return openpyxl.load_workbook(WORKBOOK_PATH, data_only=False)


def test_auction_math_workbook_exists_and_has_expected_sheets() -> None:
    assert WORKBOOK_PATH.is_file(), f"Missing spreadsheet: {WORKBOOK_PATH}"
    wb = _load_workbook()
    try:
        expected_sheets = [
            "Summary & Comparison",
            "Dallas County",
            "Pinellas County",
            "Cook County",
        ]
        assert wb.sheetnames == expected_sheets
    finally:
        wb.close()


def test_summary_sheet_inputs_formulas_formatting_and_verdicts() -> None:
    wb = _load_workbook()
    try:
        ws = wb["Summary & Comparison"]
        headers = tuple(ws.cell(row=1, column=col).value for col in range(1, 12))
        assert headers == SUMMARY_HEADERS

        expected_rows = (
            ("Dallas County, Texas", "48113", 125.0, 2.00, 4.00, 0.05, 0.10),
            ("Pinellas County, Florida", "12103", 125.0, 4.50, 9.00, 0.06, 0.10),
            ("Cook County, Illinois", "17031", 125.0, 11.00, 15.00, 0.05, 0.08),
        )
        for row_idx, expected in enumerate(expected_rows, start=2):
            values = tuple(ws.cell(row=row_idx, column=col).value for col in range(1, 8))
            assert values == expected

            best_cpl = str(ws.cell(row=row_idx, column=8).value)
            worst_cpl = str(ws.cell(row=row_idx, column=9).value)
            max_cpc = str(ws.cell(row=row_idx, column=10).value)
            verdict = str(ws.cell(row=row_idx, column=11).value)

            assert best_cpl == f"=D{row_idx}/G{row_idx}"
            assert worst_cpl == f"=E{row_idx}/F{row_idx}"
            assert max_cpc == f"=C{row_idx}*F{row_idx}"
            assert verdict == (
                f'=IF(I{row_idx}<=C{row_idx},"GREEN",IF(H{row_idx}<=C{row_idx},"YELLOW","RED"))'
            )

            assert ws.cell(row=row_idx, column=3).number_format == "$#,##0.00"
            assert ws.cell(row=row_idx, column=6).number_format == "0.0%"
            assert ws.cell(row=row_idx, column=8).number_format == "$#,##0.00"
            assert ws.cell(row=row_idx, column=1).font.bold is True
            assert ws.cell(row=row_idx, column=11).font.bold is True

        cf_rules = list(ws.conditional_formatting)
        assert len(cf_rules) >= 1
        formulas_text = " ".join(
            str(rule.formula)
            for cf in cf_rules
            for rule in cf.rules
        )
        for token in ('"GREEN"', '"YELLOW"', '"RED"'):
            assert token in formulas_text
    finally:
        wb.close()


def test_county_sensitivity_sheets_have_real_cpl_formulas() -> None:
    wb = _load_workbook()
    try:
        for county in DEMO_COUNTIES:
            ws = wb[county.sheet_name]
            assert str(ws["B3"].value).startswith("='Summary & Comparison'!C")
            assert str(ws["E4"].value).startswith("='Summary & Comparison'!K")

            header_row = 7
            first_data_row = 8
            for row_offset, cpc in enumerate(county.cpc_steps):
                row_idx = first_data_row + row_offset
                assert ws.cell(row=row_idx, column=1).value == cpc
                for col_offset, cvr in enumerate(county.cvr_steps):
                    col_idx = 2 + col_offset
                    assert ws.cell(row=header_row, column=col_idx).value == cvr
                    cell_val = str(ws.cell(row=row_idx, column=col_idx).value)
                    assert cell_val.startswith("=")
                    assert f"$A{row_idx}/" in cell_val
                    assert f"${header_row}" in cell_val
    finally:
        wb.close()


def test_playbook_readme_contains_exact_prompts_and_compliance_guardrails() -> None:
    assert README_PATH.is_file(), f"Missing playbook markdown: {README_PATH}"
    readme = README_PATH.read_text(encoding="utf-8")

    assert "auction-math.xlsx" in readme
    assert CENSUS_SOURCE in readme
    assert NOAA_SOURCE in readme

    county_records = load_county_table(COUNTIES_PARQUET_PATH)
    verticals = load_verticals_config().verticals
    motivated_seller = verticals["motivated_seller"]
    dallas = county_records["48113"]
    facts = _build_sample_verified_facts(dallas)

    expected_prompts = (
        build_trigger_interpretation_prompt(dallas, motivated_seller),
        build_qualification_prompt(dallas.county_name, motivated_seller, facts),
        build_ads_and_lp_prompt(dallas.county_name, motivated_seller, facts),
        build_followup_prompt(dallas.county_name, motivated_seller.brand_name, facts),
        build_regeneration_prompt(
            county_name=dallas.county_name,
            brand_name=motivated_seller.brand_name,
            failed_items=[
                ("headline_2", f"Exceeds {AD_HEADLINE_MAX_CHARS}-character limit (36 chars)."),
                (
                    "sms_1",
                    f'Missing opt-out keyword (e.g., "Reply STOP to opt out") and brand '
                    f'name "{motivated_seller.brand_name}".',
                ),
            ],
            vertical_config=motivated_seller,
        ),
        build_comparison_prompt(
            [
                _format_county_summary_line(county_records[c.fips], c, motivated_seller)
                for c in DEMO_COUNTIES
            ]
        ),
    )
    for prompt_text in expected_prompts:
        assert prompt_text in readme

    required_guardrail_phrases = (
        "Fair Housing (42 U.S.C. 3604(c) and (e))",
        "NO familial status limits",
        "NO blockbusting language",
        f"STRICT limit <= {AD_HEADLINE_MAX_CHARS} characters",
        f"STRICT limit <= {AD_DESCRIPTION_MAX_CHARS} characters",
        f"STRICT limit: <= {SMS_MAX_CHARS} characters per SMS",
        '"automated"',
        '"not a condition"',
        '"stop"',
        "Reply STOP to opt out",
        "Human Review Checklist",
        "review-offer-terms",
        "review-insurance-claims",
    )
    for phrase in required_guardrail_phrases:
        assert phrase in readme


def test_playbook_outputs_match_generator_with_zero_drift(tmp_path: Path) -> None:
    tmp_xlsx = tmp_path / "auction-math.xlsx"
    build_workbook(tmp_xlsx)
    assert tmp_xlsx.is_file()

    wb = openpyxl.load_workbook(tmp_xlsx, data_only=False)
    try:
        assert wb["Summary & Comparison"]["H2"].value == "=D2/G2"
    finally:
        wb.close()

    county_records = load_county_table(COUNTIES_PARQUET_PATH)
    verticals = load_verticals_config().verticals
    compliance = load_compliance_config()
    expected_readme = build_playbook_markdown(county_records, verticals, compliance)
    assert README_PATH.read_text(encoding="utf-8") == expected_readme
