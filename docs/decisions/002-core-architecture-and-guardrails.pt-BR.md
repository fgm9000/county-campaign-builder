# ADR 002 — Arquitetura do núcleo e guardrails

> 🇧🇷 PT-BR | 🇺🇸 [EN](002-core-architecture-and-guardrails.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
O PRD pede que fatos e cálculos da IA sejam conferidos (seção 5), que os ativos respeitem limites e regras (RF-03 a RF-06) e que o que o código não verifica vá para revisão humana (RF-09).

## Decisão
O LLM propõe; o código verifica, calcula e decide o status de cada item.

**Subgrafo por condado (LangGraph):**
`load_county_data` → `interpret_triggers` (Haiku) → `verify_numbers` (código) → `draft_qualification` (Haiku) → `draft_ads_and_lp` (Sonnet) → `draft_followup` (Haiku: SMS e e-mails) → `check_compliance` (código) → `regenerate_failed` (uma vez) → `compute_unit_economics` (código) → `build_review_list` (código).
O grafo principal faz o fan-out (`Send`) dos condados e termina em `compare_counties`.

**Guardrails:**
| Risco | Proteção (código) |
|---|---|
| Número inventado ou errado | Todo número citado precisa ter `field` e `value`. O código compara com a tabela do condado; o que diverge é corrigido para o valor da fonte e registrado em `corrections`, e o que não tem campo de origem é removido |
| Conta errada | A conta do leilão é só do código: CPL = CPC ÷ conversão; CPC máximo = lance × conversão; semáforo pelas faixas |
| Anúncio fora do limite | Títulos ≤ 30 caracteres e descrições ≤ 90, contados pelo código |
| SMS sem consentimento ou saída | Regra TCPA: SMS precisa identificar o remetente e trazer opt-out ("Reply STOP"); limite de 160 caracteres por segmento |
| Linguagem discriminatória em moradia | Regras de Fair Housing e da política de Housing do Google aplicadas ao texto (configuração por vertical, conferida no texto oficial antes de virar regra) |
| Promessa que o comprador do lead não cumpre | Não dá para verificar: vai para `needs_human_review`, com o motivo |

**Item reprovado:** é regenerado **uma vez** com o motivo da reprovação no prompt; se falhar de novo, sai marcado `rejected`, nunca como aprovado.

**Degradação:**
- Falha do LLM num condado → aquele condado sai `failed`, e os outros seguem; a tabela mostra o status.
- Falha na geração de um ativo → o ativo sai `missing` e entra na revisão humana.

## Justificativa
É a disciplina do briefing-scout ampliada de "trecho literal" para "número contra a fonte" e "cálculo só no código", que é exatamente o que a vaga pede ("check facts, calculations").

## Divergência do padrão
`service.py` dá lugar ao grafo; entram `rules/` por vertical e `economics.py`.

## Consequências
- Positivas: guardrails testáveis sem LLM; 100% de cobertura viável.
- Negativas: a regeneração única pode aumentar o custo por condado, a medir.
- Impacto no plano: Fases 2 a 4.

## Critério de revisão
Taxa de reprovação final acima de 10% dos ativos nos evals live: revisar prompts antes de aumentar as tentativas.
