# ADR 004 — Estratégia de avaliação

> 🇧🇷 PT-BR | 🇺🇸 [EN](004-llm-evaluation-strategy.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
A demo afirma que fatos e cálculos são conferidos e que os ativos obedecem a regras. Os evals precisam provar isso com o modelo falso no CI e com modelos reais sob demanda.

## Decisão
DeepEval, reaproveitando a estrutura do briefing-scout, incluindo o ajuste do mypy restrito a `evals.metrics`, já aceito naquele projeto.

**Métricas determinísticas (CI, modelo falso):**
- `NumericAccuracyMetric`: todo número publicado bate com a tabela do condado; a armadilha (número errado plantado) aparece em `corrections`.
- `CharacterLimitMetric`: títulos ≤ 30, descrições ≤ 90 e SMS ≤ 160, ou marcados como reprovados.
- `ComplianceMetric`: TCPA (remetente e opt-out em todo SMS) e Fair Housing (nenhum termo proibido nos ativos aprovados).
- `QualificationCoverageMetric`: as perguntas obrigatórias da vertical estão presentes (ex.: prazo de venda, condição do imóvel, se está anunciado).
- `EconomicsMetric`: o semáforo e os números batem com a fórmula, recalculada de forma independente.

**Live (manual, `LIVE_EVAL=1`):** G-Eval do copy (relevância local, clareza da oferta, ausência de clichê genérico), com juiz `claude-opus-5-5`, um modelo diferente dos geradores; mais as métricas determinísticas sobre a saída real.

## Divergência do padrão
Promptfoo sai e DeepEval entra (como no briefing-scout).

## Consequências
- Positivas: cada promessa da página tem uma métrica que a prova.
- Negativas: G-Eval com instabilidade conhecida de LLM-as-judge.
- Impacto no plano: Fase 6.

## Critério de revisão
Se o G-Eval oscilar entre rodadas acima de 0,2 no mesmo caso, rodar 3 vezes e usar a mediana.
