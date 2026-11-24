# County Campaign Builder — Non-Code Operations Playbook

> **Audience:** Performance marketing, growth, and lead-gen operations teams running county-level campaigns in **ChatGPT** or **Claude** without writing code.
> **Companion Spreadsheet:** [auction-math.xlsx](auction-math.xlsx) (live Excel / Google Sheets formulas for CPL, break-even CPC, traffic-light verdicts, and per-county sensitivity tables).
> **Prompt Sync:** Every prompt template below is generated directly from `county_campaign_builder.prompt` so the manual process and the automated pipeline never drift.

---

## Why This Playbook Exists (Division of Labor)

Asking an AI chat window to *"write a campaign for Cook County"* produces generic copy, unverified statistics, and campaigns that silently lose money on click costs. This workflow separates responsibilities into three clear lanes:

| Lane | Owner | What It Does |
|---|---|---|
| **1. Data & Auction Math** | Spreadsheet (`auction-math.xlsx`) + Public Datasets | Pulls exact `U.S. Census Bureau ACS 2020-2024` & `NOAA Storm Events 2020-2024` fields and computes CPL, Max Viable CPC, and the `GREEN` / `YELLOW` / `RED` verdict using formulas—never LLM math. |
| **2. Copy & Structuring** | ChatGPT or Claude (using the prompts below) | Turns verified county numbers into local triggers, 5 qualification questions, Google Ads RSA copy, landing page copy, SMS, and emails. |
| **3. Compliance & Judgment** | Human Operator (checklist below) | Enforces Fair Housing, TCPA consent/opt-out, quiet hours, and buyer offer terms before any campaign goes live. |

---

## Quick-Start Workflow (Step by Step)

### Step 0 — Run the Auction Math First in `auction-math.xlsx`

Before generating a single word of copy, open [auction-math.xlsx](auction-math.xlsx):

1. On the **`Summary & Comparison`** tab, enter the target county's **Lead Bid ($)**, **Min/Max CPC ($)**, and **Min/Max Landing CVR**.
2. Inspect the formula-driven outputs:
   - **Best CPL ($)** = `Min CPC / Max CVR` (`=D2/G2`)
   - **Worst CPL ($)** = `Max CPC / Min CVR` (`=E2/F2`)
   - **Max Viable CPC ($)** = `Bid * Min CVR` (`=C2*F2`)
   - **Verdict** = `=IF(I2<=C2,"GREEN",IF(H2<=C2,"YELLOW","RED"))`
3. Open the county's **Sensitivity Table** tab (`Dallas County`, `Pinellas County`, `Cook County`) where every cell computes `=RowCPC/ColCVR` and highlights viable cells (`<= Bid`) in green.

**Reference Benchmark (Motivated Seller, `$125.00` Lead Bid):**

| County (FIPS) | Bid | CPC Range | CVR Range | Best CPL | Worst CPL | Max Viable CPC | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Dallas County, Texas (`48113`) | $125.00 | $2.00–$4.00 | 5.0%–10.0% | $20.00 | $80.00 | $6.25 | **GREEN** |
| Pinellas County, Florida (`12103`) | $125.00 | $4.50–$9.00 | 6.0%–10.0% | $45.00 | $150.00 | $7.50 | **YELLOW** |
| Cook County, Illinois (`17031`) | $125.00 | $11.00–$15.00 | 5.0%–8.0% | $137.50 | $300.00 | $6.25 | **RED** |

> **Key Lesson:** Cook County has strong homeowner tenure (`31.24%` pre-2000 owners) and storm activity, so an LLM asked only about market triggers would recommend launching there. The spreadsheet catches the truth: at `$11.00–$15.00` metro CPCs and `5%–8%` CVR, even the best-case CPL (`$137.50`) exceeds the `$125.00` bid (`RED`).

---

### Step 1 — Interpret Authoritative County Data into Triggers

Paste the exact county record fields (from `data/counties.parquet` or Census ACS + NOAA Storm Events) into ChatGPT or Claude using the prompt below. Replace the county fields for your target county and vertical (`Motivated seller (cash offer)` or `Roof replacement`).

```text
You are a US local market analyst for real estate and home services lead generation.

County: Dallas County, Texas (FIPS: 48113, Storm window: 2020-2024)
Vertical: Motivated seller (cash offer)
Campaign Goal: Find owners who want to sell quickly and as-is, and qualify them before the lead is sold, so the buyer gets a better lead-to-deal ratio.

Authoritative County Record Fields (use ONLY these values):
- owner_long_tenure_pct: 26.6 [source: U.S. Census Bureau ACS 2020-2024]
- free_and_clear_pct: 42.69 [source: U.S. Census Bureau ACS 2020-2024]
- vacancy_pct: 7.72 [source: U.S. Census Bureau ACS 2020-2024]
- median_year_built: 1983 [source: U.S. Census Bureau ACS 2020-2024]
- owner_occupied_pct: 50.77 [source: U.S. Census Bureau ACS 2020-2024]
- median_home_value_usd: 303000 [source: U.S. Census Bureau ACS 2020-2024]
- tropical_events: 0 [source: NOAA Storm Events 2020-2024]
- hail_reports_1in: 102 [source: NOAA Storm Events 2020-2024]

Task:
Interpret the county data fields above into 3 to 5 concrete messaging triggers that
explain why homeowners in this county are strong prospects for this vertical.

Structured Output Requirements:
Return 3 to 5 trigger items. Every item MUST include:
- claim: concise natural-language statement linking the datum to homeowner motivation.
- field: exact column name from the Authoritative County Record Fields list above.
- value: exact numeric value (int or float) matching the county record above.
- source: exact source string, either "U.S. Census Bureau ACS 2020-2024" or "NOAA Storm Events 2020-2024".

Strict Grounding Rules:
- NEVER invent, estimate, round differently, or extrapolate numbers.
- Every claim and numeric value MUST match the county record above verbatim.
- Do NOT cite any field marked N/A (withheld by source).
- Use only the exact field names listed above.
```

**Operator Check:** Compare every returned number against your source table. If any number was rounded differently or invented, replace it with the exact source figure before proceeding to Step 2.

---

### Step 2 — Draft 5 Lead-Qualification Intake Questions

Paste the **verified facts** from Step 1 into the qualification prompt so the landing form filters tire-kickers before the lead is sold.

```text
You are a US lead-qualification strategist for real estate and home services.

Target County: Dallas County, Texas
Vertical: Motivated seller (cash offer)
Brand: Example Home Buyers
Campaign Goal: Find owners who want to sell quickly and as-is, and qualify them before the lead is sold, so the buyer gets a better lead-to-deal ratio.

Verified Local Facts (use only these if referencing local context):
- 42.69% of owner-occupied homes in Dallas County are owned without a mortgage (field: free_and_clear_pct, value: 42.69, source: U.S. Census Bureau ACS 2020-2024)
- 26.6% of owner-occupied householders moved in before 2000 (field: owner_long_tenure_pct, value: 26.6, source: U.S. Census Bureau ACS 2020-2024)
- 102 NOAA hail reports of 1 inch or larger in 2020-2024 (field: hail_reports_1in, value: 102, source: NOAA Storm Events 2020-2024)

Required Qualification Topics (and why each topic is vital):
1. Topic: timeline
   Why this matters: How soon they need to sell separates motivated sellers from browsers.
2. Topic: property_condition
   Why this matters: Repairs needed is the main reason to accept an as-is cash offer.
3. Topic: listed_with_agent
   Why this matters: A property already listed on the MLS is usually not an off-market deal.
4. Topic: decision_maker
   Why this matters: Only the owner on the title (or all owners) can sign.
5. Topic: reason_for_selling
   Why this matters: Inheritance, relocation, tired landlord or financial pressure predict a deal.

Task:
Write exactly 5 lead-qualification intake questions tailored to homeowners in
Dallas County, Texas, covering every required topic listed above (one primary question
per topic).

Structured Output Requirements:
For each of the 5 questions, return:
- question_index: integer 1 through 5.
- topic: exact topic name from the Required Qualification Topics list.
- question: clear, polite, direct intake question written in natural US English.
- why: brief explanation of why this topic is vital for lead qualification.

Rules:
- Cover all required topics with clear, unambiguous wording.
- Do NOT invent or extrapolate county statistics.
- Keep all questions respectful and Fair Housing compliant.
```

---

### Step 3 — Draft Google Responsive Search Ads & Landing Page Copy

Generate 5 to 6 headlines (`<= 30` chars), 3 to 4 descriptions (`<= 90` chars), and the above-the-fold landing page block including the mandatory TCPA written-consent disclosure.

```text
You are a senior US performance copywriter and compliance-aware marketer for
real estate and home services.

Target County: Dallas County, Texas
Brand Name: Example Home Buyers
Vertical: Motivated seller (cash offer)
Campaign Goal: Find owners who want to sell quickly and as-is, and qualify them before the lead is sold, so the buyer gets a better lead-to-deal ratio.

Verified Local Facts (cite ONLY numbers from this list):
- 42.69% of owner-occupied homes in Dallas County are owned without a mortgage (field: free_and_clear_pct, value: 42.69, source: U.S. Census Bureau ACS 2020-2024)
- 26.6% of owner-occupied householders moved in before 2000 (field: owner_long_tenure_pct, value: 26.6, source: U.S. Census Bureau ACS 2020-2024)
- 102 NOAA hail reports of 1 inch or larger in 2020-2024 (field: hail_reports_1in, value: 102, source: NOAA Storm Events 2020-2024)

Task:
Draft the Google Responsive Search Ad copy and the above-the-fold landing page
copy for Dallas County, Texas.

Structured Output Requirements:
1. Ad Copy:
   - headlines: 5 to 6 varied headlines, STRICT limit <= 30 characters each
     (including spaces and punctuation). Cover distinct fact-grounded angles: direct as-is,
     repair/maintenance relief, fast closing, zero commissions, and local presence.
   - descriptions: 3 to 4 varied descriptions, STRICT limit <= 90 characters
     each (including spaces and punctuation). Address real homeowner pressures (aging properties,
     repair costs, storm wear, holding costs).
2. Landing Page Top:
   - headline: clear, locally relevant primary headline.
   - subheadline: concise supporting statement connecting local context to fast relief.
   - cta_text: action-oriented call-to-action button text.
   - bullet_points: 4 to 5 homeowner benefit bullet points addressing real burdens
     (as-is purchase, skipping costly updates on aging systems, zero commissions,
     7-14 day close, local specialist). Do NOT paste raw census or demographic
     percentages here; keep bullets homeowner-facing.
   - consent_disclosure: TCPA written-consent statement placed by the form that
     MUST include all three required phrases (case-insensitive): "automated",
     "not a condition", and "stop" (for example: consent to receive automated
     calls/texts, consent is not a condition of purchase, reply STOP to opt out).

Data-to-Pain-Point Translation Guidance:
- Older housing stock / median build year -> Address deferred maintenance, costly
  roof/plumbing/electrical updates, or avoiding contractor headaches.
- Severe storm / hail events -> Address storm damage wear, roof leak fatigue, and
  bypassing insurance repairs.
- High vacancy / long tenure -> Address ongoing property taxes, upkeep on empty
  or inherited homes, and tired landlords.
- NEVER cite raw statistics, Census percentages, or storm counts to the seller;
  translate every fact into the concrete financial, emotional, or logistical
  burden it creates for the homeowner.

Mandatory Fair Housing & Compliance Rules:
- Fair Housing (42 U.S.C. 3604(c) and (e)): NEVER use discriminatory language or
  state preferences or limitations based on race, color, religion, sex, disability,
  familial status, or national origin.
- NO familial status limits (e.g., never say "adults only", "no kids",
  "without children", "perfect for singles", or "not suitable for families").
- NO blockbusting language (e.g., never say "neighborhood is changing",
  "sell before values decline", or "new residents are moving in").
- Ground all local claims in the Verified Local Facts above; NEVER invent numbers.
- Avoid unverifiable promises (e.g., guaranteed outcomes, free roof, or fixed
  closing-day guarantees).
```

---

### Step 4 — Draft Speed-to-Lead SMS & Email Follow-Ups

Generate 2 TCPA-compliant SMS messages (`<= 160` chars, exact brand name + `"Reply STOP to opt out"`) and 2 helpful follow-up emails.

```text
You are a US lifecycle copywriter for real estate acquisitions.
Your audience is motivated homeowners seeking a direct as-is cash sale.

Target County: Dallas County, Texas
Brand Name: Example Home Buyers

Audience Context & Problem Translation:
The homeowner wants to sell directly to avoid expensive repairs, contractor headaches,
agent commissions, holding costs (taxes/insurance on vacant homes), or closing delays.
Translate local market pressures (older homes, storm wear, inheritance/vacancy) into
empathetic, respectful follow-up copy focused entirely on their relief and timeline.
Do NOT cite macro census or weather statistics in seller communications.

Verified Local Facts (for internal market reference):
- 42.69% of owner-occupied homes in Dallas County are owned without a mortgage (field: free_and_clear_pct, value: 42.69, source: U.S. Census Bureau ACS 2020-2024)
- 26.6% of owner-occupied householders moved in before 2000 (field: owner_long_tenure_pct, value: 26.6, source: U.S. Census Bureau ACS 2020-2024)
- 102 NOAA hail reports of 1 inch or larger in 2020-2024 (field: hail_reports_1in, value: 102, source: NOAA Storm Events 2020-2024)

Task:
Write 2 SMS follow-up messages and 2 email follow-ups for leads in Dallas County, Texas.

Structured Output Requirements:
1. sms_messages (exactly 2 items, message_index 1 and 2):
   - STRICT limit: <= 160 characters per SMS (including spaces,
     punctuation, brand name, and opt-out text).
   - Each SMS MUST include the exact brand name "Example Home Buyers".
   - Each SMS MUST include a clear opt-out instruction (e.g., "Reply STOP to opt out").
2. email_followups (exactly 2 items, email_index 1 and 2):
   - Email 1: Focus on selling as-is to skip major repair estimates or storm wear.
   - Email 2: Focus on financial certainty—zero fees, zero holding costs, and closing.
   - Each email MUST include a subject line and clear, helpful body text.

Compliance & Grounding Rules:
- Follow Fair Housing rules: no discriminatory preferences, familial status limits,
  or blockbusting language.
- Avoid unverifiable guarantees or promises.
```

---

### Step 5 — Fix Only Rejected Assets (Targeted Regeneration)

If any headline exceeds `30` characters, any description exceeds `90` characters, any SMS exceeds `160` characters, or any compliance phrase is missing, do **not** regenerate the whole campaign. Paste only the failed items into this prompt:

```text
You are a US campaign compliance editor rewriting ONLY rejected campaign assets.

Target County: Dallas County, Texas
Brand Name: Example Home Buyers
Vertical: Motivated seller (cash offer)
Campaign Goal: Find owners who want to sell quickly and as-is, and qualify them before the lead is sold, so the buyer gets a better lead-to-deal ratio.

Failed Assets to Rewrite:
1. Item: headline_2
   Current invalid text / rejection reason: Exceeds 30-character limit (36 chars).
2. Item: sms_1
   Current invalid text / rejection reason: Missing opt-out keyword (e.g., "Reply STOP to opt out") and brand name "Example Home Buyers".

Task:
Rewrite ONLY the specific failed items listed above so every item passes validation.
Do NOT modify or regenerate any assets that are not listed above.
For each failed item, inspect its identifier, current invalid text (or summary),
and exact rejection reason, then return a compliant replacement.

Compliance Constraints (apply all rules relevant to each failed item):
- Ad headlines: STRICT <= 30 characters.
- Ad descriptions: STRICT <= 90 characters.
- SMS messages: STRICT <= 160 characters, MUST contain exact brand
  name "Example Home Buyers", and MUST include an opt-out keyword
  (e.g., "Reply STOP to opt out").
- Landing page consent_disclosure: MUST include "automated", "not a condition",
  and "stop" (case-insensitive).
- Fair Housing: NO discriminatory language, NO familial status limits, and NO
  blockbusting ("neighborhood is changing", etc.).
- Grounding: NEVER invent numbers or make unverifiable guarantees.
```

---

### Step 6 — Compare Multiple Counties for Launch Prioritization

Once each candidate county has verified triggers and a spreadsheet verdict from `auction-math.xlsx`, run the executive comparison prompt to pick the launch order:

```text
You are a US performance marketing director evaluating county-level campaigns.

County Campaign Summaries:
County Summary 1:
County: Dallas County, Texas (FIPS 48113) | Vertical: Motivated seller (cash offer) | Verdict: GREEN | Bid: $125.00 | Best CPL: $20.00 | Worst CPL: $80.00 | Max Viable CPC: $6.25 | Triggers: hail_reports_1in=102 (NOAA Storm Events 2020-2024), severe_wind_reports=50 (NOAA Storm Events 2020-2024), tropical_events=0 (NOAA Storm Events 2020-2024), median_year_built=1983 (U.S. Census Bureau ACS 2020-2024), vacancy_pct=7.72% (U.S. Census Bureau ACS 2020-2024), owner_long_tenure_pct=26.6% (U.S. Census Bureau ACS 2020-2024), free_and_clear_pct=42.69% (U.S. Census Bureau ACS 2020-2024)

County Summary 2:
County: Pinellas County, Florida (FIPS 12103) | Vertical: Motivated seller (cash offer) | Verdict: YELLOW | Bid: $125.00 | Best CPL: $45.00 | Worst CPL: $150.00 | Max Viable CPC: $7.50 | Triggers: hail_reports_1in=1 (NOAA Storm Events 2020-2024), severe_wind_reports=16 (NOAA Storm Events 2020-2024), tropical_events=18 (NOAA Storm Events 2020-2024), median_year_built=1977 (U.S. Census Bureau ACS 2020-2024), vacancy_pct=17.62% (U.S. Census Bureau ACS 2020-2024), owner_long_tenure_pct=22.82% (U.S. Census Bureau ACS 2020-2024), free_and_clear_pct=48.91% (U.S. Census Bureau ACS 2020-2024)

County Summary 3:
County: Cook County, Illinois (FIPS 17031) | Vertical: Motivated seller (cash offer) | Verdict: RED | Bid: $125.00 | Best CPL: $137.50 | Worst CPL: $300.00 | Max Viable CPC: $6.25 | Triggers: hail_reports_1in=94 (NOAA Storm Events 2020-2024), severe_wind_reports=455 (NOAA Storm Events 2020-2024), tropical_events=0 (NOAA Storm Events 2020-2024), median_year_built=1961 (U.S. Census Bureau ACS 2020-2024), vacancy_pct=7.74% (U.S. Census Bureau ACS 2020-2024), owner_long_tenure_pct=31.24% (U.S. Census Bureau ACS 2020-2024), free_and_clear_pct=37.61% (U.S. Census Bureau ACS 2020-2024)

Task:
Write a concise executive summary comparing these counties and recommending which
county should be prioritized for campaign launch.

Your comparison MUST address:
1. Unit Economics (Traffic Light): compare green, yellow, and red verdicts,
   best-case vs. worst-case CPL relative to lead bid, and max viable CPC.
2. Market Triggers: compare the strength and relevance of verified local triggers
   from Census ACS and NOAA storm records.
3. Launch Recommendation: identify the top-priority county (name and FIPS if
   available), explain the rationale, and note any economic or compliance caveats
   (especially if top candidates are yellow or red).

Rules:
- Base your analysis strictly on the summaries above.
- NEVER invent numbers, alter traffic-light verdicts, or extrapolate metrics.
```

---

## Compliance Guardrails (Non-Negotiable)

> **Disclaimer:** Automated checks against public rule texts; not legal advice. A human reviews every package before use.

### 1. Character Limits
- **Google Ads Headlines:** `<= 30` characters (including spaces and punctuation)
- **Google Ads Descriptions:** `<= 90` characters (including spaces and punctuation)
- **SMS Messages (1 GSM-7 segment):** `<= 160` characters (including brand name and opt-out text)

### 2. Fair Housing Act (`42 U.S.C. 3604(c) and (e); 24 CFR 100.75 (read 2026-11-19 at law.cornell.edu)`)
Protected classes: race, color, religion, sex, handicap, familial status, national origin.

- **fha-familial-status** (42 U.S.C. 3604(c); 24 CFR 100.75(c)(1)): Ad copy must not state a preference or limitation based on familial status.
- **fha-religion-national-origin-race** (42 U.S.C. 3604(c); 24 CFR 100.75(c)(1)): Ad copy must not reference race, color, religion or national origin as a preference or as a description of the people in an area.
- **fha-disability** (42 U.S.C. 3604(c); 24 CFR 100.75(c)(1)): Ad copy must not exclude or discourage people with disabilities.
- **fha-blockbusting** (42 U.S.C. 3604(e)): Ad copy must not urge owners to sell because of who is moving into the neighborhood (blockbusting).

### 3. TCPA SMS & Written Consent (`47 CFR 64.1200(a)(2), (a)(9), (a)(10), (c)(1), (d)(4), (f)(9) (read 2026-11-19); FCC 26-67, Federal Register 2026-21821, section B, effective 2026-11-25`)
Accepted opt-out keywords: `STOP`, `QUIT`, `END`, `REVOKE`, `OPT OUT`, `CANCEL`, `UNSUBSCRIBE`.

- **tcpa-opt-out-in-every-sms** (47 CFR 64.1200(a)(10); FCC 26-67 section B): Every SMS discloses how to revoke consent with at least one standardized word (for example 'Reply STOP to opt out').
- **tcpa-sender-identification** (47 CFR 64.1200(d)(4)): Every SMS identifies the sender by the brand name of the package.
- **tcpa-written-consent** (47 CFR 64.1200(a)(2), (f)(9)): The lead form shows a consent statement: the person agrees to receive automated marketing texts and calls at the number provided, consent is not a condition of any purchase, and they can reply STOP to opt out.
- **tcpa-quiet-hours** (47 CFR 64.1200(c)(1)): Texts are sent only between 8 a.m. and 9 p.m. in the recipient's local time. The package cannot schedule sends, so this always goes to human review.

---

## Human Review Checklist (Before Launching Any County)

Even when AI copy passes length and compliance checks, an operator must sign off on everything automation cannot verify:

- [ ] **Source Fact Verification:** Every county statistic cited in triggers, ads, landing pages, SMS, and emails matches `U.S. Census Bureau ACS 2020-2024` or `NOAA Storm Events 2020-2024` verbatim (zero rounded, extrapolated, or `N/A` withheld numbers).
- [ ] **Auction Economics Sign-Off:** Confirmed the county verdict in [auction-math.xlsx](auction-math.xlsx) (`GREEN` or approved `YELLOW` with CPC cap). Do **not** launch `RED` counties without lowering target CPC or raising buyer lead bid.
- [ ] **Qualification Coverage:** Confirmed all 5 vertical-required intake questions are present and aligned with lead-buyer qualification criteria.
- [ ] **review-offer-terms:** Verify any flagged claim — Promises a price, speed or fee condition that only the buyer of the lead can confirm.
- [ ] **review-insurance-claims:** Verify any flagged claim — Talks about insurance coverage or claims, which depend on each policy.
- [ ] **TCPA Consent & Quiet Hours:** Confirmed the landing page form displays the written-consent disclosure (`"automated"`, `"not a condition"`, `"stop"`), every SMS identifies the exact brand name + `"Reply STOP to opt out"`, and SMS scheduling is restricted to **8:00 a.m. – 9:00 p.m. recipient local time**.
- [ ] **Fair Housing & Local Nuance:** Read all headlines, descriptions, landing copy, SMS, and emails end-to-end to confirm respectful, non-discriminatory wording and true local relevance.
