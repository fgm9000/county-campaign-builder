# ADR 007 — Reaproveitamento do motor do briefing-scout

> 🇧🇷 PT-BR | 🇺🇸 [EN](007-reuse-from-briefing-scout.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
O briefing-scout está pronto e testado. O prazo desta demo é de 1 semana.

## Opções consideradas
| Opção | Prós | Contras |
|-------|------|---------|
| **A — Copiar e adaptar** | Rápido; não mexe no projeto pronto | Duplicação entre os dois repositórios |
| B — Biblioteca compartilhada | Sem duplicação | Dias de refatoração nos dois projetos; acoplamento |

## Decisão
Opção A. Entram, adaptados:
- `models` (contratos base), `limits`, `settings`, a estrutura de `api` (SSE, código de acesso, logs), `llm` (cliente Anthropic e modelo falso) e o padrão de `graph`;
- a catraca, os workflows (com `permissions` desde o início), o Dockerfile, o `.gitattributes`, o export de cenários e a estrutura da página.

Não entram: `agency`, `memory`, `embeddings`, `netguard` e o verificador de trecho literal, que é substituído pelo numérico.

## Divergência do padrão
Nenhuma.

## Consequências
- Positivas: semana focada no domínio novo.
- Negativas / dívidas: correções futuras no motor precisam ser repetidas nos dois repositórios.
- Impacto no plano: Fase 1.

## Critério de revisão
Uma terceira demo com o mesmo motor: extrair uma biblioteca comum.
