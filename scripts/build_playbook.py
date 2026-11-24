"""Generate the non-code playbook (playbook/README.md) and spreadsheet (playbook/auction-math.xlsx).

Imports prompt builders and compliance/vertical configs directly from ``county_campaign_builder``
so the manual ChatGPT/Claude workflow stays in lockstep with the production codebase.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from county_campaign_builder.county_data import CountyRecord, load_county_table
from county_campaign_builder.domain import (
    ComplianceConfig,
    VerticalConfig,
    load_compliance_config,
    load_verticals_config,
)
from county_campaign_builder.economics import calculate_unit_economics
from county_campaign_builder.models import NumericFact, NumericRange
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

PLAYBOOK_DIR = REPO_ROOT / "playbook"
WORKBOOK_PATH = PLAYBOOK_DIR / "auction-math.xlsx"
README_PATH = PLAYBOOK_DIR / "README.md"
COUNTIES_PARQUET_PATH = REPO_ROOT / "data" / "counties.parquet"

CURRENCY_FORMAT = "$#,##0.00"
PERCENT_FORMAT = "0.0%"
TEXT_FORMAT = "@"

HEADER_FILL = PatternFill(fill_type="solid", start_color="1F3864", end_color="1F3864")
SUBHEADER_FILL = PatternFill(fill_type="solid", start_color="D9E1F2", end_color="D9E1F2")
FORMULA_FILL = PatternFill(fill_type="solid", start_color="F2F5F9", end_color="F2F5F9")
GREEN_FILL = PatternFill(fill_type="solid", start_color="C6EFCE", end_color="C6EFCE")
YELLOW_FILL = PatternFill(fill_type="solid", start_color="FFEB9C", end_color="FFEB9C")
RED_FILL = PatternFill(fill_type="solid", start_color="FFC7CE", end_color="FFC7CE")

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=13, bold=True, color="1F3864")
BOLD_FONT = Font(name="Calibri", size=11, bold=True, color="000000")
BODY_FONT = Font(name="Calibri", size=11, bold=False, color="000000")
MUTED_FONT = Font(name="Calibri", size=10, italic=True, color="404040")
GREEN_FONT = Font(name="Calibri", size=11, bold=True, color="006100")
YELLOW_FONT = Font(name="Calibri", size=11, bold=True, color="9C6500")
RED_FONT = Font(name="Calibri", size=11, bold=True, color="9C0006")

THIN_SIDE = Side(style="thin", color="BFBFBF")
HEADER_SIDE = Side(style="thin", color="1F3864")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
HEADER_BORDER = Border(left=HEADER_SIDE, right=HEADER_SIDE, top=HEADER_SIDE, bottom=HEADER_SIDE)

SUMMARY_HEADERS = (
    "County",
    "FIPS",
    "Bid ($)",
    "Min CPC ($)",
    "Max CPC ($)",
    "Min CVR",
    "Max CVR",
    "Best CPL ($)",
    "Worst CPL ($)",
    "Max Viable CPC ($)",
    "Verdict",
)


@dataclass(frozen=True)
class CountyAssumption:
    """Auction assumption inputs and sensitivity grid axes for one demo county."""

    sheet_name: str
    county_name: str
    fips: str
    bid_usd: float
    min_cpc_usd: float
    max_cpc_usd: float
    min_cvr: float
    max_cvr: float
    cpc_steps: tuple[float, ...]
    cvr_steps: tuple[float, ...]


DEMO_COUNTIES: tuple[CountyAssumption, ...] = (
    CountyAssumption(
        sheet_name="Dallas County",
        county_name="Dallas County, Texas",
        fips="48113",
        bid_usd=125.0,
        min_cpc_usd=2.00,
        max_cpc_usd=4.00,
        min_cvr=0.05,
        max_cvr=0.10,
        cpc_steps=(1.50, 2.00, 2.50, 3.00, 3.50, 4.00, 4.50, 5.00),
        cvr_steps=(0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12),
    ),
    CountyAssumption(
        sheet_name="Pinellas County",
        county_name="Pinellas County, Florida",
        fips="12103",
        bid_usd=125.0,
        min_cpc_usd=4.50,
        max_cpc_usd=9.00,
        min_cvr=0.06,
        max_cvr=0.10,
        cpc_steps=(3.50, 4.50, 5.50, 6.50, 7.50, 8.50, 9.00, 10.50),
        cvr_steps=(0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12),
    ),
    CountyAssumption(
        sheet_name="Cook County",
        county_name="Cook County, Illinois",
        fips="17031",
        bid_usd=125.0,
        min_cpc_usd=11.00,
        max_cpc_usd=15.00,
        min_cvr=0.05,
        max_cvr=0.08,
        cpc_steps=(6.00, 8.00, 10.00, 11.00, 12.00, 13.00, 14.00, 15.00, 16.00),
        cvr_steps=(0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10),
    ),
)


def _add_verdict_conditional_formatting(ws: Any, cell_range: str) -> None:
    """Apply GREEN / YELLOW / RED traffic-light conditional formatting to ``cell_range``."""
    rules = (
        ('"GREEN"', GREEN_FILL, GREEN_FONT),
        ('"YELLOW"', YELLOW_FILL, YELLOW_FONT),
        ('"RED"', RED_FILL, RED_FONT),
    )
    for formula_literal, fill, font in rules:
        ws.conditional_formatting.add(
            cell_range,
            CellIsRule(operator="equal", formula=[formula_literal], fill=fill, font=font),
        )


def _auto_fit_columns(ws: Any, min_width: int = 12, padding: int = 4) -> None:
    """Adjust column widths to fit cell contents with generous padding."""
    for column_cells in ws.columns:
        max_len = 0
        col_idx = column_cells[0].column
        for cell in column_cells:
            if cell.row == 1 and ws.title != "Summary & Comparison":
                continue
            value_str = str(cell.value or "")
            if value_str.startswith("="):
                value_str = "$999.99"
            max_len = max(max_len, len(value_str))
        ws.column_dimensions[get_column_letter(col_idx)].width = max(min_width, max_len + padding)


def _populate_summary_sheet(ws: Any, counties: tuple[CountyAssumption, ...]) -> None:
    """Build the Summary & Comparison sheet with real Excel formulas and styling."""
    ws.title = "Summary & Comparison"
    ws.views.sheetView[0].showGridLines = True
    ws.freeze_panes = "A2"

    for col_idx, header in enumerate(SUMMARY_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = HEADER_BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 28

    for row_idx, county in enumerate(counties, start=2):
        row_values: tuple[tuple[Any, str, bool, bool], ...] = (
            (county.county_name, TEXT_FORMAT, True, False),
            (county.fips, TEXT_FORMAT, False, False),
            (county.bid_usd, CURRENCY_FORMAT, False, False),
            (county.min_cpc_usd, CURRENCY_FORMAT, False, False),
            (county.max_cpc_usd, CURRENCY_FORMAT, False, False),
            (county.min_cvr, PERCENT_FORMAT, False, False),
            (county.max_cvr, PERCENT_FORMAT, False, False),
            (f"=D{row_idx}/G{row_idx}", CURRENCY_FORMAT, False, True),
            (f"=E{row_idx}/F{row_idx}", CURRENCY_FORMAT, False, True),
            (f"=C{row_idx}*F{row_idx}", CURRENCY_FORMAT, False, True),
            (
                f'=IF(I{row_idx}<=C{row_idx},"GREEN",IF(H{row_idx}<=C{row_idx},"YELLOW","RED"))',
                TEXT_FORMAT,
                True,
                True,
            ),
        )
        for col_idx, (val, num_fmt, is_bold, is_formula) in enumerate(row_values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.number_format = num_fmt
            cell.font = BOLD_FONT if is_bold else BODY_FONT
            cell.border = CELL_BORDER
            if is_formula:
                cell.fill = FORMULA_FILL
            if col_idx in (2, 11):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 1:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[row_idx].height = 22

    last_row = 1 + len(counties)
    _add_verdict_conditional_formatting(ws, f"K2:K{last_row}")

    legend_start = last_row + 2
    legend_rows = (
        ("Formula & Traffic-Light Guide", ""),
        ("Best CPL ($)", "= Min CPC / Max CVR (favorable auction and landing conversion)"),
        ("Worst CPL ($)", "= Max CPC / Min CVR (conservative auction and landing conversion)"),
        ("Max Viable CPC ($)", "= Bid * Min CVR (break-even CPC at worst-case CVR)"),
        ("GREEN", "Worst CPL <= Bid: profitable across the entire assumed CPC/CVR range"),
        ("YELLOW", "Best CPL <= Bid < Worst CPL: profitable only in favorable conditions"),
        ("RED", "Best CPL > Bid: unit economics do not close anywhere in the range"),
    )
    for offset, (label, description) in enumerate(legend_rows):
        row = legend_start + offset
        label_cell = ws.cell(row=row, column=1, value=label)
        desc_cell = ws.cell(row=row, column=2, value=description)
        if offset == 0:
            label_cell.font = BOLD_FONT
        else:
            label_cell.font = BOLD_FONT
            desc_cell.font = MUTED_FONT

    _auto_fit_columns(ws)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["K"].width = 14


def _populate_county_sheet(
    ws: Any,
    county: CountyAssumption,
    summary_row: int,
) -> None:
    """Create a per-county sensitivity tab with ``=RowCPC/ColCVR`` formulas."""
    ws.views.sheetView[0].showGridLines = True

    title = ws.cell(
        row=1,
        column=1,
        value=f"{county.county_name} (FIPS {county.fips}) — CPL Sensitivity Table",
    )
    title.font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    summary_ref = "'Summary & Comparison'"
    assumptions: tuple[tuple[str, str, str], ...] = (
        ("Lead Bid ($)", f"={summary_ref}!C{summary_row}", CURRENCY_FORMAT),
        ("Min / Max CPC ($)", f"={summary_ref}!D{summary_row}", CURRENCY_FORMAT),
        ("Min / Max CVR", f"={summary_ref}!F{summary_row}", PERCENT_FORMAT),
    )
    for offset, (label, formula, num_fmt) in enumerate(assumptions, start=3):
        lbl = ws.cell(row=offset, column=1, value=label)
        lbl.font = BOLD_FONT
        lbl.fill = SUBHEADER_FILL
        lbl.border = CELL_BORDER

        val = ws.cell(row=offset, column=2, value=formula)
        val.number_format = num_fmt
        val.font = BODY_FONT
        val.border = CELL_BORDER
        val.alignment = Alignment(horizontal="right", vertical="center")

    max_cpc_cell = ws.cell(row=4, column=3, value=f"={summary_ref}!E{summary_row}")
    max_cpc_cell.number_format = CURRENCY_FORMAT
    max_cpc_cell.font = BODY_FONT
    max_cpc_cell.border = CELL_BORDER

    max_cvr_cell = ws.cell(row=5, column=3, value=f"={summary_ref}!G{summary_row}")
    max_cvr_cell.number_format = PERCENT_FORMAT
    max_cvr_cell.font = BODY_FONT
    max_cvr_cell.border = CELL_BORDER

    ws.cell(row=3, column=4, value="Max Viable CPC ($)").font = BOLD_FONT
    viable_cell = ws.cell(row=3, column=5, value=f"={summary_ref}!J{summary_row}")
    viable_cell.number_format = CURRENCY_FORMAT
    viable_cell.font = BOLD_FONT
    viable_cell.border = CELL_BORDER

    ws.cell(row=4, column=4, value="Summary Verdict").font = BOLD_FONT
    verdict_cell = ws.cell(row=4, column=5, value=f"={summary_ref}!K{summary_row}")
    verdict_cell.font = BOLD_FONT
    verdict_cell.border = CELL_BORDER
    verdict_cell.alignment = Alignment(horizontal="center", vertical="center")
    _add_verdict_conditional_formatting(ws, "E4:E4")

    header_row = 7
    corner = ws.cell(row=header_row, column=1, value="CPC \\ CVR")
    corner.font = HEADER_FONT
    corner.fill = HEADER_FILL
    corner.border = HEADER_BORDER
    corner.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[header_row].height = 24

    for col_offset, cvr in enumerate(county.cvr_steps, start=2):
        cvr_cell = ws.cell(row=header_row, column=col_offset, value=cvr)
        cvr_cell.number_format = PERCENT_FORMAT
        cvr_cell.font = HEADER_FONT
        cvr_cell.fill = HEADER_FILL
        cvr_cell.border = HEADER_BORDER
        cvr_cell.alignment = Alignment(horizontal="center", vertical="center")

    first_data_row = header_row + 1
    for row_offset, cpc in enumerate(county.cpc_steps):
        row_idx = first_data_row + row_offset
        cpc_cell = ws.cell(row=row_idx, column=1, value=cpc)
        cpc_cell.number_format = CURRENCY_FORMAT
        cpc_cell.font = BOLD_FONT
        cpc_cell.fill = SUBHEADER_FILL
        cpc_cell.border = CELL_BORDER
        cpc_cell.alignment = Alignment(horizontal="right", vertical="center")

        for col_offset in range(len(county.cvr_steps)):
            col_idx = 2 + col_offset
            col_letter = get_column_letter(col_idx)
            formula = f"=$A{row_idx}/{col_letter}${header_row}"
            cpl_cell = ws.cell(row=row_idx, column=col_idx, value=formula)
            cpl_cell.number_format = CURRENCY_FORMAT
            cpl_cell.font = BODY_FONT
            cpl_cell.border = CELL_BORDER
            cpl_cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[row_idx].height = 20

    last_data_row = first_data_row + len(county.cpc_steps) - 1
    last_col_letter = get_column_letter(1 + len(county.cvr_steps))
    grid_range = f"B{first_data_row}:{last_col_letter}{last_data_row}"
    ws.conditional_formatting.add(
        grid_range,
        CellIsRule(
            operator="lessThanOrEqual",
            formula=["$B$3"],
            fill=GREEN_FILL,
            font=GREEN_FONT,
        ),
    )
    ws.conditional_formatting.add(
        grid_range,
        CellIsRule(
            operator="greaterThan",
            formula=["$B$3"],
            fill=RED_FILL,
            font=RED_FONT,
        ),
    )

    _auto_fit_columns(ws)
    ws.column_dimensions["A"].width = 20


def build_workbook(
    output_path: Path,
    counties: tuple[CountyAssumption, ...] = DEMO_COUNTIES,
) -> None:
    """Create and save the multi-sheet auction math workbook with Excel formulas."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    summary_ws = wb.active
    _populate_summary_sheet(summary_ws, counties)

    for idx, county in enumerate(counties, start=2):
        county_ws = wb.create_sheet(title=county.sheet_name)
        _populate_county_sheet(county_ws, county, summary_row=idx)

    wb.save(output_path)


def _format_county_summary_line(
    record: CountyRecord,
    assumption: CountyAssumption,
    vertical: VerticalConfig,
) -> str:
    """Format one county summary line using real auction economics for the comparison prompt."""
    econ = calculate_unit_economics(
        bid_per_lead_usd=assumption.bid_usd,
        cpc_usd=NumericRange(min=assumption.min_cpc_usd, max=assumption.max_cpc_usd),
        landing_cvr=NumericRange(min=assumption.min_cvr, max=assumption.max_cvr),
    )
    return (
        f"County: {record.county_name} (FIPS {record.fips}) | Vertical: {vertical.label} | "
        f"Verdict: {econ.verdict.upper()} | Bid: ${econ.bid_per_lead_usd:.2f} | "
        f"Best CPL: ${econ.cpl_best_usd:.2f} | Worst CPL: ${econ.cpl_worst_usd:.2f} | "
        f"Max Viable CPC: ${econ.max_cpc_usd:.2f} | "
        f"Triggers: hail_reports_1in={record.hail_reports_1in} ({NOAA_SOURCE}), "
        f"severe_wind_reports={record.severe_wind_reports} ({NOAA_SOURCE}), "
        f"tropical_events={record.tropical_events} ({NOAA_SOURCE}), "
        f"median_year_built={record.median_year_built} ({CENSUS_SOURCE}), "
        f"vacancy_pct={record.vacancy_pct}% ({CENSUS_SOURCE}), "
        f"owner_long_tenure_pct={record.owner_long_tenure_pct}% ({CENSUS_SOURCE}), "
        f"free_and_clear_pct={record.free_and_clear_pct}% ({CENSUS_SOURCE})"
    )


def _build_sample_verified_facts(dallas: CountyRecord) -> list[NumericFact]:
    """Build verified NumericFact examples grounded in the authoritative Dallas County record."""
    return [
        NumericFact(
            claim=(
                f"{dallas.free_and_clear_pct}% of owner-occupied homes in Dallas County "
                "are owned without a mortgage"
            ),
            field="free_and_clear_pct",
            value=float(dallas.free_and_clear_pct or 0.0),
            source=CENSUS_SOURCE,
            status="verified",
        ),
        NumericFact(
            claim=(
                f"{dallas.owner_long_tenure_pct}% of owner-occupied householders moved in "
                "before 2000"
            ),
            field="owner_long_tenure_pct",
            value=float(dallas.owner_long_tenure_pct or 0.0),
            source=CENSUS_SOURCE,
            status="verified",
        ),
        NumericFact(
            claim=(
                f"{dallas.hail_reports_1in} NOAA hail reports of 1 inch or larger in "
                f"{dallas.years_covered}"
            ),
            field="hail_reports_1in",
            value=dallas.hail_reports_1in,
            source=NOAA_SOURCE,
            status="verified",
        ),
    ]


def _render_compliance_section(compliance: ComplianceConfig) -> str:
    """Render Fair Housing, TCPA, and character-limit rules from ``config/compliance.json``."""
    fair_housing_lines = "\n".join(
        f"- **{rule.rule_id}** ({rule.reference}): {rule.description}"
        for rule in compliance.fair_housing.rules
    )
    tcpa_lines = "\n".join(
        f"- **{rule.rule_id}** ({rule.reference}): {rule.description}"
        for rule in compliance.tcpa_sms.rules
    )
    opt_out_words = ", ".join(f"`{kw}`" for kw in compliance.tcpa_sms.opt_out_keywords)

    return (
        "## Compliance Guardrails (Non-Negotiable)\n\n"
        f"> **Disclaimer:** {compliance.disclaimer}\n\n"
        "### 1. Character Limits\n"
        f"- **Google Ads Headlines:** `<= {AD_HEADLINE_MAX_CHARS}` characters "
        "(including spaces and punctuation)\n"
        f"- **Google Ads Descriptions:** `<= {AD_DESCRIPTION_MAX_CHARS}` characters "
        "(including spaces and punctuation)\n"
        f"- **SMS Messages (1 GSM-7 segment):** `<= {SMS_MAX_CHARS}` characters "
        "(including brand name and opt-out text)\n\n"
        f"### 2. Fair Housing Act (`{compliance.fair_housing.source}`)\n"
        f"Protected classes: {', '.join(compliance.fair_housing.protected_classes)}.\n\n"
        f"{fair_housing_lines}\n\n"
        f"### 3. TCPA SMS & Written Consent (`{compliance.tcpa_sms.source}`)\n"
        f"Accepted opt-out keywords: {opt_out_words}.\n\n"
        f"{tcpa_lines}\n"
    )


def _render_human_review_checklist(compliance: ComplianceConfig) -> str:
    """Render the mandatory pre-launch human review checklist."""
    review_rules = "\n".join(
        f"- [ ] **{rule.rule_id}:** Verify any flagged claim — {rule.reason}"
        for rule in compliance.human_review_patterns.rules
    )
    return (
        "## Human Review Checklist (Before Launching Any County)\n\n"
        "Even when AI copy passes length and compliance checks, an operator must sign off on "
        "everything automation cannot verify:\n\n"
        "- [ ] **Source Fact Verification:** Every county statistic cited in triggers, ads, "
        f"landing pages, SMS, and emails matches `{CENSUS_SOURCE}` or `{NOAA_SOURCE}` verbatim "
        "(zero rounded, extrapolated, or `N/A` withheld numbers).\n"
        "- [ ] **Auction Economics Sign-Off:** Confirmed the county verdict in "
        "[auction-math.xlsx](auction-math.xlsx) (`GREEN` or approved `YELLOW` with CPC cap). "
        "Do **not** launch `RED` counties without lowering target CPC or raising buyer lead bid.\n"
        "- [ ] **Qualification Coverage:** Confirmed all 5 vertical-required intake questions "
        "are present and aligned with lead-buyer qualification criteria.\n"
        f"{review_rules}\n"
        "- [ ] **TCPA Consent & Quiet Hours:** Confirmed the landing page form displays the "
        'written-consent disclosure (`"automated"`, `"not a condition"`, `"stop"`), every SMS '
        'identifies the exact brand name + `"Reply STOP to opt out"`, and SMS scheduling is '
        "restricted to **8:00 a.m. – 9:00 p.m. recipient local time**.\n"
        "- [ ] **Fair Housing & Local Nuance:** Read all headlines, descriptions, landing copy, "
        "SMS, and emails end-to-end to confirm respectful, non-discriminatory wording and true "
        "local relevance.\n"
    )


def build_playbook_markdown(
    county_records: dict[str, CountyRecord],
    verticals: dict[str, VerticalConfig],
    compliance: ComplianceConfig,
) -> str:
    """Assemble the complete non-code playbook markdown using live prompt builders."""
    motivated_seller = verticals["motivated_seller"]
    roofing = verticals["roofing"]
    dallas_record = county_records["48113"]
    verified_facts = _build_sample_verified_facts(dallas_record)

    trigger_prompt = build_trigger_interpretation_prompt(dallas_record, motivated_seller)
    qualification_prompt = build_qualification_prompt(
        dallas_record.county_name, motivated_seller, verified_facts
    )
    ads_lp_prompt = build_ads_and_lp_prompt(
        dallas_record.county_name, motivated_seller, verified_facts
    )
    followup_prompt = build_followup_prompt(
        dallas_record.county_name, motivated_seller.brand_name, verified_facts
    )
    regeneration_prompt = build_regeneration_prompt(
        county_name=dallas_record.county_name,
        brand_name=motivated_seller.brand_name,
        failed_items=[
            (
                "headline_2",
                f"Exceeds {AD_HEADLINE_MAX_CHARS}-character limit (36 chars).",
            ),
            (
                "sms_1",
                f'Missing opt-out keyword (e.g., "Reply STOP to opt out") and brand '
                f'name "{motivated_seller.brand_name}".',
            ),
        ],
        vertical_config=motivated_seller,
    )
    comparison_summaries = [
        _format_county_summary_line(county_records[assumption.fips], assumption, motivated_seller)
        for assumption in DEMO_COUNTIES
    ]
    comparison_prompt = build_comparison_prompt(comparison_summaries)

    econ_rows = []
    for assumption in DEMO_COUNTIES:
        econ = calculate_unit_economics(
            bid_per_lead_usd=assumption.bid_usd,
            cpc_usd=NumericRange(min=assumption.min_cpc_usd, max=assumption.max_cpc_usd),
            landing_cvr=NumericRange(min=assumption.min_cvr, max=assumption.max_cvr),
        )
        econ_rows.append(
            f"| {assumption.county_name} (`{assumption.fips}`) | "
            f"${assumption.bid_usd:,.2f} | "
            f"${assumption.min_cpc_usd:,.2f}–${assumption.max_cpc_usd:,.2f} | "
            f"{assumption.min_cvr * 100:.1f}%–{assumption.max_cvr * 100:.1f}% | "
            f"${econ.cpl_best_usd:,.2f} | ${econ.cpl_worst_usd:,.2f} | "
            f"${econ.max_cpc_usd:,.2f} | **{econ.verdict.upper()}** |"
        )
    econ_table = "\n".join(econ_rows)

    compliance_section = _render_compliance_section(compliance)
    checklist_section = _render_human_review_checklist(compliance)

    sections = [
        "# County Campaign Builder — Non-Code Operations Playbook\n",
        (
            "> **Audience:** Performance marketing, growth, and lead-gen operations teams running "
            "county-level campaigns in **ChatGPT** or **Claude** without writing code.\n"
            "> **Companion Spreadsheet:** [auction-math.xlsx](auction-math.xlsx) (live Excel / "
            "Google Sheets formulas for CPL, break-even CPC, traffic-light verdicts, and "
            "per-county sensitivity tables).\n"
            "> **Prompt Sync:** Every prompt template below is generated directly from "
            "`county_campaign_builder.prompt` so the manual process and the automated pipeline "
            "never drift.\n"
        ),
        "---\n",
        "## Why This Playbook Exists (Division of Labor)\n",
        (
            'Asking an AI chat window to *"write a campaign for Cook County"* produces generic '
            "copy, unverified statistics, and campaigns that silently lose money on click costs. "
            "This workflow separates responsibilities into three clear lanes:\n"
        ),
        (
            "| Lane | Owner | What It Does |\n"
            "|---|---|---|\n"
            f"| **1. Data & Auction Math** | Spreadsheet (`auction-math.xlsx`) + Public Datasets "
            f"| Pulls exact `{CENSUS_SOURCE}` & `{NOAA_SOURCE}` fields and computes CPL, Max "
            "Viable CPC, and the `GREEN` / `YELLOW` / `RED` verdict using formulas—never LLM "
            "math. |\n"
            "| **2. Copy & Structuring** | ChatGPT or Claude (using the prompts below) | Turns "
            "verified county numbers into local triggers, 5 qualification questions, Google Ads "
            "RSA copy, landing page copy, SMS, and emails. |\n"
            "| **3. Compliance & Judgment** | Human Operator (checklist below) | Enforces Fair "
            "Housing, TCPA consent/opt-out, quiet hours, and buyer offer terms before any "
            "campaign goes live. |\n"
        ),
        "---\n",
        "## Quick-Start Workflow (Step by Step)\n",
        "### Step 0 — Run the Auction Math First in `auction-math.xlsx`\n",
        "Before generating a single word of copy, open [auction-math.xlsx](auction-math.xlsx):\n",
        (
            "1. On the **`Summary & Comparison`** tab, enter the target county's **Lead Bid ($)**, "
            "**Min/Max CPC ($)**, and **Min/Max Landing CVR**.\n"
            "2. Inspect the formula-driven outputs:\n"
            "   - **Best CPL ($)** = `Min CPC / Max CVR` (`=D2/G2`)\n"
            "   - **Worst CPL ($)** = `Max CPC / Min CVR` (`=E2/F2`)\n"
            "   - **Max Viable CPC ($)** = `Bid * Min CVR` (`=C2*F2`)\n"
            '   - **Verdict** = `=IF(I2<=C2,"GREEN",IF(H2<=C2,"YELLOW","RED"))`\n'
            "3. Open the county's **Sensitivity Table** tab (`Dallas County`, `Pinellas County`, "
            "`Cook County`) where every cell computes `=RowCPC/ColCVR` and highlights viable "
            "cells (`<= Bid`) in green.\n"
        ),
        "**Reference Benchmark (Motivated Seller, `$125.00` Lead Bid):**\n",
        (
            "| County (FIPS) | Bid | CPC Range | CVR Range | Best CPL | Worst CPL "
            "| Max Viable CPC | Verdict |\n"
            "|---|---:|---:|---:|---:|---:|---:|---|\n"
            f"{econ_table}\n"
        ),
        (
            "> **Key Lesson:** Cook County has strong homeowner tenure (`31.24%` pre-2000 owners) "
            "and storm activity, so an LLM asked only about market triggers would recommend "
            "launching there. The spreadsheet catches the truth: at `$11.00–$15.00` metro CPCs "
            "and `5%–8%` CVR, even the best-case CPL (`$137.50`) exceeds the `$125.00` bid "
            "(`RED`).\n"
        ),
        "---\n",
        "### Step 1 — Interpret Authoritative County Data into Triggers\n",
        (
            "Paste the exact county record fields (from `data/counties.parquet` or Census ACS + "
            "NOAA Storm Events) into ChatGPT or Claude using the prompt below. Replace the county "
            f"fields for your target county and vertical (`{motivated_seller.label}` or "
            f"`{roofing.label}`).\n"
        ),
        f"```text\n{trigger_prompt}\n```\n",
        (
            "**Operator Check:** Compare every returned number against your source table. If any "
            "number was rounded differently or invented, replace it with the exact source figure "
            "before proceeding to Step 2.\n"
        ),
        "---\n",
        "### Step 2 — Draft 5 Lead-Qualification Intake Questions\n",
        (
            "Paste the **verified facts** from Step 1 into the qualification prompt so the landing "
            "form filters tire-kickers before the lead is sold.\n"
        ),
        f"```text\n{qualification_prompt}\n```\n",
        "---\n",
        "### Step 3 — Draft Google Responsive Search Ads & Landing Page Copy\n",
        (
            f"Generate 5 to 6 headlines (`<= {AD_HEADLINE_MAX_CHARS}` chars), 3 to 4 descriptions "
            f"(`<= {AD_DESCRIPTION_MAX_CHARS}` chars), and the above-the-fold landing page block "
            "including the mandatory TCPA written-consent disclosure.\n"
        ),
        f"```text\n{ads_lp_prompt}\n```\n",
        "---\n",
        "### Step 4 — Draft Speed-to-Lead SMS & Email Follow-Ups\n",
        (
            f"Generate 2 TCPA-compliant SMS messages (`<= {SMS_MAX_CHARS}` chars, exact brand name "
            '+ `"Reply STOP to opt out"`) and 2 helpful follow-up emails.\n'
        ),
        f"```text\n{followup_prompt}\n```\n",
        "---\n",
        "### Step 5 — Fix Only Rejected Assets (Targeted Regeneration)\n",
        (
            f"If any headline exceeds `{AD_HEADLINE_MAX_CHARS}` characters, any description "
            f"exceeds `{AD_DESCRIPTION_MAX_CHARS}` characters, any SMS exceeds `{SMS_MAX_CHARS}` "
            "characters, or any compliance phrase is missing, do **not** regenerate the whole "
            "campaign. Paste only the failed items into this prompt:\n"
        ),
        f"```text\n{regeneration_prompt}\n```\n",
        "---\n",
        "### Step 6 — Compare Multiple Counties for Launch Prioritization\n",
        (
            "Once each candidate county has verified triggers and a spreadsheet verdict from "
            "`auction-math.xlsx`, run the executive comparison prompt to pick the launch order:\n"
        ),
        f"```text\n{comparison_prompt}\n```\n",
        "---\n",
        compliance_section,
        "---\n",
        checklist_section.rstrip("\n"),
    ]
    return "\n".join(sections) + "\n"


def main() -> int:
    """Generate ``playbook/auction-math.xlsx`` and ``playbook/README.md``."""
    county_records = load_county_table(COUNTIES_PARQUET_PATH)
    verticals = load_verticals_config().verticals
    compliance = load_compliance_config()

    build_workbook(WORKBOOK_PATH)
    readme_text = build_playbook_markdown(county_records, verticals, compliance)
    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(readme_text, encoding="utf-8")

    print(f"wrote {WORKBOOK_PATH}")
    print(f"wrote {README_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
