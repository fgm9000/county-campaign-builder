# ADR 001 — Stack and Tooling

> 🇺🇸 EN | 🇧🇷 [PT-BR](001-stack-and-tooling.pt-BR.md) · Status: Accepted (Gate 2, 2026-11-19) · Date: 2026-11-19

## Context
1-week timeline (PRD, Section 10). The `briefing-scout` engine already solves graph orchestration, verification, API, safeguards, evals, and CI/CD (ADR 007). Local sources are structured (ADR 006), so there is no web search: LLM calls are for interpretation and generation with structured output.

## Options Considered
| Area | Option | Pros | Cons |
|------|--------|------|------|
| S1 | **Python 3.12 (standard)** | Full reuse of the engine | No new language |
| S6 | **Anthropic: Haiku 5.5 + Sonnet 5.5** | Reuses client and evals; strong copy models | Repeats `briefing-scout`'s provider |
| S6 | OpenAI (GPT) | New repertoire; posting mentions "ChatGPT" | Rebuilding client, fake model, and evals within 1 week |
| S6 | Anthropic with Opus for copy | Maximum quality | Per-county cost and latency |
| S7 | **LangGraph with fan-out (`Send`)** | Counties in parallel; new technical evidence | Watch API rate limits |
| S7 | Linear LangGraph | Direct reuse | ~3× slower |

## Decision
- **S1, S2, and S4:** Python 3.12, uv, Ruff, mypy `--strict`, Pytest, and Pydantic v2.
- **S6:** Anthropic API. `claude-haiku-5-5` interprets county data and writes qualification questions, SMS, and emails; `claude-sonnet-5-5` writes ads and the LP hero. Structured output on all calls.
- **S7:** LangGraph with **fan-out via `Send`**: one subgraph per county in parallel, and a reducer node that builds the comparison table.
- **S3:** FastAPI with SSE, emitting per-county and per-step events.
- **S5:** No database. Precomputed table of all counties (ADR 006).
- **S8:** DeepEval (ADR 004). **S13:** PII-free JSON logs.
- **New:** Polars for the ETL (ADR 006) and openpyxl for the playbook spreadsheet (ADR 008).

## Rationale
With structured sources and 1 week, switching LLM providers would cost rebuilding the client, fake model, and evals without product gain. The demo's new technical evidence comes from fan-out, public-data ETL in Polars, the numeric verifier, and the playbook with spreadsheet—which is what this role evaluates.

## Deviations from Standard
| Item | Standard | Decision | Trade-off |
|------|----------|----------|-----------|
| Provider | OpenRouter | Direct Anthropic | Model switching is no longer free; `ModelClient` remains a `Protocol` with fake model |
| Orchestration | Custom pipeline | LangGraph with fan-out | More dependencies; nodes remain pure testable functions |
| Evaluation | Promptfoo | DeepEval | See ADR 004 |

## Consequences
- Positive: high reuse; latency for 3 counties close to 1 county.
- Negative / debt: same provider dependency as `briefing-scout`.
- Plan impact: Phases 1, 3, and 4.

## Review Criterion
Measured cost above $0.30 per county, or Sonnet copy failing G-Eval: revisit model split.
