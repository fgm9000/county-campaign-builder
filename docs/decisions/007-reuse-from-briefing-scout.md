# ADR 007 — Reuse from briefing-scout Engine

> 🇺🇸 EN | 🇧🇷 [PT-BR](007-reuse-from-briefing-scout.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
`briefing-scout` is complete and tested. This demo's timeline is 1 week.

## Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **A — Copy and adapt** | Fast; does not touch the finished project | Duplication between the two repositories |
| B — Shared library | No duplication | Days of refactoring across both projects; coupling |

## Decision
Option A. Brought over and adapted:
- `models` (base contracts), `limits`, `settings`, `api` structure (SSE, access code, logs), `llm` (Anthropic client and fake model), and `graph` pattern;
- the ratchet, workflows (with `permissions` from the start), Dockerfile, `.gitattributes`, scenario export, and page structure.

Excluded: `agency`, `memory`, `embeddings`, `netguard`, and the verbatim-quote verifier, which is replaced by the numeric verifier.

## Deviations from Standard
None.

## Consequences
- Positive: week focused on the new domain.
- Negative / debt: future engine fixes must be applied to both repositories.
- Plan impact: Phase 1.

## Review Criterion
A third demo using the same engine: extract a shared library.
