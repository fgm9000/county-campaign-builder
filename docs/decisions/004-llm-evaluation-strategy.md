# ADR 004 — LLM Evaluation Strategy

> 🇺🇸 EN | 🇧🇷 [PT-BR](004-llm-evaluation-strategy.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
The demo claims that facts and calculations are checked and that assets obey rules. Evals must prove this with the fake model in CI and with real models on demand.

## Decision
DeepEval, reusing the `briefing-scout` structure, including the mypy override scoped to `evals.metrics`, already accepted in that project.

**Deterministic metrics (CI, fake model):**
- `NumericAccuracyMetric`: every published number matches the county table; the planted trap (wrong number) appears in `corrections`.
- `CharacterLimitMetric`: headlines ≤ 30, descriptions ≤ 90, and SMS ≤ 160, or marked rejected.
- `ComplianceMetric`: TCPA (sender and opt-out in every SMS) and Fair Housing (no prohibited terms in approved assets).
- `QualificationCoverageMetric`: mandatory questions for the vertical are present (e.g., selling timeline, property condition, whether listed).
- `EconomicsMetric`: traffic light and numbers match the independently recalculated formula.

**Live (manual, `LIVE_EVAL=1`):** G-Eval on copy (local relevance, offer clarity, absence of generic clichés) with `claude-opus-5-5` as judge—a different model from the generators—plus the deterministic metrics on real output.

## Deviations from Standard
Promptfoo is replaced by DeepEval (as in `briefing-scout`).

## Consequences
- Positive: every claim on the page has a metric proving it.
- Negative: known LLM-as-judge variance on G-Eval.
- Plan impact: Phase 6.

## Review Criterion
If G-Eval varies by more than 0.2 across runs on the same case, run 3 times and take the median.
