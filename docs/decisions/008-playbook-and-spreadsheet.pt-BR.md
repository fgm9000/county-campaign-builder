# ADR 008 — Playbook não-código e planilha

> 🇧🇷 PT-BR | 🇺🇸 [EN](008-playbook-and-spreadsheet.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
A vaga pede processos que outras pessoas sigam, sem exigir programação (RF-10).

## Decisão
- **`playbook/README.md`** (inglês): o workflow etapa por etapa para rodar no Claude ou no ChatGPT, com os mesmos prompts do código, a checklist de revisão humana e as regras de compliance em linguagem simples.
- **`playbook/auction-math.xlsx`:** gerada por `scripts/build_playbook.py` com openpyxl, com **fórmulas reais** (CPL, CPC máximo e semáforo por formatação condicional) e uma aba por condado da demo.
- Os prompts do playbook são lidos do mesmo módulo de prompts do código, e um teste falha se os dois divergirem.

## Divergência do padrão
Entregável fora do Padrão Mestre, motivado pela vaga.

## Consequências
- Positivas: prova "documents, spreadsheets" e "processes others can use".
- Impacto no plano: Fase 9.

## Critério de revisão
Corte nº 2 do PRD: se o prazo apertar, a planilha cai e a conta fica só no Markdown.
