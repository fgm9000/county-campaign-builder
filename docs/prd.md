# PRD — county-campaign-builder

> 🇺🇸 EN | 🇧🇷 [PT-BR](prd.pt-BR.md) · Status: Approved on 2026-11-19 (Gate 1) · Version 1.0 · Started on 2026-11-19

## 0. Framing (Stage 0, closed on 2026-11-19)
- **Working name:** county-campaign-builder
- **One-sentence problem:** Scale local lead-gen campaigns (motivated sellers and roofing) across many U.S. counties without falling back to generic copy, with every local claim checked against its source and auction math verified by code.
- **Type:** Portfolio demo (`fgm9000`) built for the "Marketing AI & Automation Builder" real estate lead-gen teams. English-first. May stay private until submission.
- **Repository:** `C:\Users\fabio\development\county-campaign-builder` (alongside the other demos, outside Google Drive).
- **Relationship to briefing-scout:** Reuses the engine (graph, citation verifier, vertical rules, evals, pipeline). `briefing-scout` remains untouched.

## 1. Context and Problem
- **Core demo story:** The same workflow runs across **3 counties side by side** and ends in a comparison table: what changes from one county to another (triggers, questions, ads) and in which county the auction math fails to pencil out. It proves scale and decision-making, not just the quality of a single asset pack.
- **Verticals:** **motivated seller** (cash offer) as the primary vertical and **roof replacement** as the second configuration of the same engine. Switching requires only configuration changes (questions, rules, triggers), with no code changes, proving the workflow is reusable.
- **Operator and evaluator:** See Section 2.

## 2. Objective and Value Proposition
For lead-gen teams that need to launch local campaigns across many U.S. counties, `county-campaign-builder` turns public county-level data into a review-ready campaign pack: qualification questions, ads, landing page copy, SMS, and emails. Every local number is checked against the source, auction math is computed by code, and anything requiring human judgment is flagged. Using ChatGPT alone produces generic copy, with no verifiable source and no check on whether the campaign pencils out.

- **Competencies the demo proves** (in the job description's language): turning an ambiguous business problem into a multi-step AI workflow; checking AI-generated facts and calculations; building a reusable process others can follow; explaining where AI adds value and where human judgment is needed.
- **Target evaluator:** The marketing or operations stakeholder, likely from marketing or operations rather than an engineer. That is why the first screen speaks business (cost per lead, bid) and the playbook requires no coding.
- **Operator in the story:** The "Marketing AI & Automation Builder" themselves, or someone on the marketing team running the workflow.

## 3. Scope
### 3.1 In MVP
For each county, the pack delivers:
- RF-01 — Local brief: source-checked county facts (see Section 7).
- RF-02 — Landing page form qualification questions, by vertical (separating leads that close into deals from those that do not).
- RF-03 — Google Search Ad (RSA): 8 headlines and 3 descriptions.
- RF-04 — Landing page hero: headline, subheadline, and CTA.
- RF-05 — 3 speed-to-lead SMS messages (first few minutes after signup).
- RF-06 — Follow-up email sequence (Fabio's decision on 2026-11-19; exact length to be finalized).
- RF-07 — Auction math: estimated CPL vs. county bid, with visible assumptions.
- RF-08 — Comparison table across the 3 counties (Section 1).
- RF-09 — Human review per pack: `needs human review` list with the reason for each item (Section 8).
- RF-10 — No-code playbook:
  - Markdown with reusable prompts for each step, a guide for using them in Claude or ChatGPT, and a review checklist;
  - `.xlsx` auction-math spreadsheet with visible formulas.

  Both are generated from the same source the code uses so they never drift.

### 3.2 Out of Scope
- Images, video, and affiliates: next steps in the README.
- Campaign targeting (ZIP code, audience profile): the demo generates copy and unit economics, not audience setup. Housing policy is therefore enforced as a text rule.

## 4. Main Flow
**Recorded demo counties**, chosen for contrast:
| County | What the data shows (2020–2024 & ACS 2020–2024) | Expected traffic light |
|---|---|---|
| Dallas County, TX | 102 hail reports ≥ 1"; newer homes (1983); 42.7% owned free and clear | 🟢 pencils out |
| Pinellas County, FL | 18 tropical events; 17.6% vacancy; 48.9% owned free and clear; homes built 1977 | 🟡 borderline |
| Cook County, IL | 455 wind reports and 94 hail reports; older homes (1961); 31.2% of owners in place > 25 years | 🔴 strong triggers, but metro click cost fails auction math |

**2026-11-20 Revision (Phase 2):** The initial narrative assumed "Cook with few weather events," and the data showed the opposite. Cook remains red, now for a more instructive reason: AI would recommend it based on triggers, and code rejects it based on auction math. CPC remains an operator assumption, labeled as such on screen.

**Steps:**
1. The operator provides the county (FIPS code), vertical, bid per lead, and **assumptions** for CPC and landing page conversion rate (min–max range).
2. Code loads the county aggregates (NOAA and ACS) and builds the sources.
3. The LLM turns the data into messaging triggers, each citing its number and source.
4. Code checks every number against the source; any mismatch is corrected or removed, and the correction is shown.
5. The LLM generates the qualification questions, ad copy, LP hero, SMS, and emails.
6. Code enforces character limits, TCPA, Fair Housing, and vertical rules; failures are regenerated once and, if they persist, marked rejected.
7. Code computes the auction math and traffic light, and builds the human review list.
8. Across the 3 counties, code builds the comparison table.

**Auction math (code only):**
- CPL = CPC ÷ LP conversion rate.
- Max CPC that pencils out = bid × conversion rate.
- Traffic light: green if worst-case CPL in the range fits within the bid; yellow if it fits only in the best case; red if it fits in neither.

Example input (illustrative; final contract defined in Phase 2):
```json
{
  "county_fips": "48113",
  "vertical": "motivated_seller",
  "bid_per_lead_usd": 125,
  "cpc_usd": {"min": 4.5, "max": 9.0},
  "landing_cvr": {"min": 0.06, "max": 0.10}
}
```
Example output (illustrative excerpt):
```json
{
  "county": "Dallas County, TX",
  "facts": [{"claim": "34 hail reports of 1 inch or larger in 2025", "value": 34, "source": "NOAA Storm Events", "status": "verified"}],
  "corrections": [{"llm_value": 41, "source_value": 34, "field": "hail_reports_2025"}],
  "unit_economics": {"cpl_best_usd": 45.0, "cpl_worst_usd": 150.0, "max_cpc_usd": 7.5, "verdict": "yellow"},
  "needs_human_review": [{"item": "headline_5", "reason": "Promises a 7-day close; confirm the offer terms with the buyer"}]
}
```

## 5. Technical Differentiator (30-Second Rule)
On the first screen, two things side by side:
1. **The 3-county table with the auction-math traffic light.** One county in red, with the math exposed: "at $9 CPC and 6% conversion, a lead costs $150; the bid is $125: does not pencil out." The math belongs to code, never the LLM.
2. **A number the AI got wrong and code corrected.** For example: "AI wrote 41 hail reports; NOAA records 34." Demonstrates the numeric verifier against a structured source.

Together, these embody the job description's "check AI-generated facts, calculations, and recommendations." Compliance checks (TCPA, Fair Housing, character limits) appear inside each pack.

## 6. Non-Functional Requirements
**Access modes** (same model as `briefing-scout`):
- **Public:** page with the 3 precomputed counties, zero runtime cost.
- **Live:** with an access code, runs any chosen county on the spot (the "pick a county" interview moment).

| ID | Requirement | Target | Source / Hypothesis |
|----|-------------|--------|---------------------|
| RNF-01 | Cost per live county | ≤ $0.30 | Hypothesis: more generated text than `briefing-scout` (~$0.05); measure in Phase 4 |
| RNF-02 | Time per live county | ≤ 90 s, with per-step progress | Hypothesis, to be measured |
| RNF-03 | Monthly provider cap | $30 (same as Anthropic Console limit) | Prior decision by Fabio |
| RNF-04 | Live-mode safeguards | Access code, rate limit, PII-free logs | Reused from `briefing-scout` |
| RNF-05 | Language | UI and outputs in English (U.S. market); docs PT/EN | Stage 0 |

## 7. Data and Privacy
- **Local facts come from structured public data, not web search:**
  - **Motivated seller, primary signals (Census ACS):** housing age, vacancy rate, renter-occupied share (investor-owned proxy), owners in place over 25 years (B25038), and homes owned free and clear (B25081). Included in Phase 2 at Fabio's request because weather is a secondary trigger for home sellers.
  - **Weather (NOAA Storm Events):** primary trigger for roofing and secondary angle for motivated seller (storm-damaged property sold as-is).
  - Foreclosure and tax-delinquency data would be stronger signals, but they are paid datasets (ATTOM and similar): left as a next step. Code downloads the numbers; the LLM only writes from them; the verifier also checks cited **numbers**.
- **Versioned snapshot** of the 3-county data so CI and the public page work offline.
- Availability, format, license, and limits of both sources: to be confirmed at the source in Stage 2.
- **PII:** none. Data consists of public county aggregates; live mode receives no personal data, and logs follow `briefing-scout`'s PII-free pattern.

## 8. Use of AI
**Division of labor, explicit in the demo:**
| Actor | Responsibility |
|---|---|
| AI (LLM) | Interprets county data into messaging triggers; drafts questions, ads, LP copy, SMS, and emails |
| Code | Fetches and aggregates data; verifies numbers and sources; computes auction math; enforces character limits, TCPA, and Fair Housing |
| Human | Reviews what code cannot verify |

- **Mandatory human review per pack:** every item code cannot verify (offer promise, competitor angle, tone, local fit) is flagged `needs human review` with a reason. This turns the job description's "when human judgment is needed" into a product feature.
- **LLM failure handling:** a number that disagrees with the source is corrected or removed by code; text that violates a limit or rule is rejected and regenerated once, and if it persists it is marked rejected (never delivered as approved). Auction math never depends on the LLM.
- **Eval metrics:** to be defined in Stage 2 (candidates: numeric accuracy against the source, rule compliance, qualification-question coverage, and a copy-quality rubric).

## 9. Success Metrics
- **Application:** demo submitted with the application by 2026-11-26, with a public link, English README, and an optional short video.
- **30 seconds:** an evaluator sees the traffic light and the corrected number without scrolling.
- **Quality:** green evals in CI; zero published numbers disagreeing with the source; 100% of assets within limits and rules, or marked rejected.
- **Reuse:** the second vertical (roofing) runs solely with new configuration, with zero code changes.

## 10. Constraints, Timeline, and Dependencies
- **Target date:** demo ready to submit with the application on **2026-11-26** (1 week, Fabio's decision on 2026-11-19).
- **Budget:** $30/month on the LLM provider, same cap; Cloud Run in the shared `fgm9000-portfolio` project.
- **External dependencies:** NOAA Storm Events and Census ACS (data), LLM provider.
- **Scope cuts if timeline tightens, in order:** (1) email sequence; (2) `.xlsx` spreadsheet, leaving only Markdown; (3) live mode, leaving only the precomputed scenarios.

## 11. Assumptions and Open Questions
| Item | Adopted Assumption | Review Criterion |
|------|--------------------|------------------|
| NOAA & Census sources | County-level aggregates are accessible under an open-use license | Confirm at the source in Stage 2 |
| 3-county narrative | Dallas pencils out, Pinellas is borderline, Cook fails | Verify against real data before recording |
| CPC & conversion assumptions | Operator provides ranges; demo uses illustrative values and states this on screen | Never present as market data |
| TCPA & Fair Housing rules | Text checks (opt-out, discriminatory language) | Check official text before encoding as rules |
| Cost & latency per county | ≤ $0.30 and ≤ 90 s | First real measurement |
| 1-week timeline | Fits by reusing the engine | Review at the end of the domain phase |

## 12. Stack Pre-Decisions to Confirm in Stage 2
- Reuse from `briefing-scout`: LangGraph graph, `domain.py` (citation verifier, vertical rules), Pydantic contracts, ratchet, DeepEval evals, CI pipeline, and deployment.
- Candidate public sources: NOAA Storm Events (hail and wind by county) and Census ACS (housing age, owner occupancy). Availability, format, and limits to confirm at the source.
- No-code deliverable: playbook (reusable prompts and templates) + auction-math spreadsheet.
- Live mode for any county without downloading NOAA on the fly: evaluate precomputing aggregates for **all ~3,200 counties** (NOAA + ACS) into a small versioned table so live mode does not depend on an external data API.

## Job Posting Context (Reference)
"Marketing AI & Automation Builder", real estate lead-gen teams, remote South America. Points the demo must prove, in the posting's own words:
- "Turn an ambiguous business problem into a structured, multi-step AI workflow."
- "Check AI-generated facts, calculations, and recommendations rather than accepting them at face value."
- "Build reusable processes that consistently produce useful outputs."
- "Explain where AI adds value, where it struggles, and when human judgment is needed."
- Domains: motivated seller leads (core business; metric "lead-to-deal ratio"), roofing & home services, affiliates.
- "Advanced coding skills… are not required": the evaluator is likely not an engineer.
