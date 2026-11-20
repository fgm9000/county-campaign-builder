# ADR 002 — Core Architecture and Guardrails

> 🇺🇸 EN | 🇧🇷 [PT-BR](002-core-architecture-and-guardrails.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
The PRD requires AI facts and calculations to be verified (Section 5), assets to obey limits and rules (RF-03 to RF-06), and anything code cannot verify to go to human review (RF-09).

## Decision
The LLM proposes; code verifies, calculates, and decides the status of every item.

**Per-county subgraph (LangGraph):**
`load_county_data` → `interpret_triggers` (Haiku) → `verify_numbers` (code) → `draft_qualification` (Haiku) → `draft_ads_and_lp` (Sonnet) → `draft_followup` (Haiku: SMS and emails) → `check_compliance` (code) → `regenerate_failed` (once) → `compute_unit_economics` (code) → `build_review_list` (code).
The main graph fans out (`Send`) across counties and ends at `compare_counties`.

**Guardrails:**
| Risk | Protection (code) |
|---|---|
| Invented or wrong number | Every cited number must include `field` and `value`. Code compares against the county table; mismatches are corrected to the source value and logged in `corrections`, and values without a source field are removed |
| Wrong math | Auction math lives only in code: CPL = CPC ÷ conversion; max CPC = bid × conversion; traffic light across ranges |
| Ad over character limit | Headlines ≤ 30 chars and descriptions ≤ 90 chars, counted by code |
| SMS without consent or opt-out | TCPA rule: SMS must identify the sender and include opt-out ("Reply STOP"); 160-character limit per segment |
| Discriminatory housing language | Fair Housing and Google Housing policy rules applied to copy (per-vertical config, checked against official text before becoming rules) |
| Promise the lead buyer cannot fulfill | Cannot be verified automatically: goes to `needs_human_review` with the reason |

**Rejected item:** regenerated **once** with the rejection reason in the prompt; if it fails again, it is marked `rejected`, never approved.

**Degradation:**
- LLM failure on one county → that county exits `failed`, and the others continue; the table shows the status.
- Failure generating a single asset → the asset exits `missing` and enters human review.

## Rationale
This extends `briefing-scout`'s discipline from "verbatim quote" to "number against source" and "math in code only"—which is exactly what the job posting asks for ("check facts, calculations").

## Deviations from Standard
`service.py` is replaced by the graph; per-vertical `rules/` and `economics.py` are introduced.

## Consequences
- Positive: guardrails testable without an LLM; 100% coverage achievable.
- Negative: single regeneration may increase per-county cost, to be measured.
- Plan impact: Phases 2 to 4.

## Review Criterion
Final rejection rate above 10% of assets in live evals: revise prompts before increasing retries.
