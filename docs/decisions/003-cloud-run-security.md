# ADR 003 — Cloud Run and Security

> 🇺🇸 EN | 🇧🇷 [PT-BR](003-cloud-run-security.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
Live mode runs a county chosen during an interview (PRD, Section 6). The `briefing-scout` infrastructure in `fgm9000-portfolio` (WIF pool, account/secret pattern, deployment) is already proven.

## Decision
New Cloud Run service, `county-campaign-builder`, in the same project and with the same design:
- runtime account with zero project-level roles, with access only to its own secrets;
- deploy account with `run.developer`, `artifactregistry.writer` on the repository, and `serviceAccountUser` only on the runtime account;
- dedicated WIF provider, restricted to the repository and `main`;
- `--min-instances=0 --max-instances=1 --memory=512Mi --timeout=120`;
- secrets: Anthropic and access code. Census does not go to production (ADR 006);
- reused safeguards: access code with failed-attempt lockout, per-IP rate limit, PII-free logs, `hide_input_in_errors`.

**Difference from `briefing-scout`:** live input is a county FIPS code and numbers, not a URL. `netguard` is not needed because the server makes no external fetches other than the LLM; input validation checks that the FIPS code exists in the table.

## Deviations from Standard
None beyond `--timeout=120` (SSE), already accepted in `briefing-scout`. Initial service bootstrap by the project owner is documented in the runbook (the deploy account does not enable `--no-invoker-iam-check`).

## Consequences
- Positive: repeated, documented infrastructure; smaller attack surface (no arbitrary URL input).
- Negative: one additional service in the shared project.
- Plan impact: Phase 8.

## Review Criterion
Cold start above 15 s or RAM above 400 MB.
