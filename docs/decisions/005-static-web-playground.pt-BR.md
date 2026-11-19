# ADR 005 — Static Web Playground

> 🇧🇷 PT-BR | 🇺🇸 [EN](005-static-web-playground.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
Quem avalia provavelmente é de marketing ou operações (PRD, seção 2) e precisa ver o semáforo e o número corrigido em 30 segundos (seção 5).

## Decisão
Página estática no GitHub Pages, reaproveitando a estrutura do briefing-scout:
- **inglês como padrão**, com PT como segunda língua;
- primeira tela: a **tabela dos 3 condados com o semáforo** e o **número corrigido**, sem rolar;
- abaixo, um condado aberto por vez: fatos com fonte, perguntas, anúncios com a contagem de caracteres visível, LP, SMS, e-mails e a lista de revisão humana;
- aba ao vivo: FIPS, vertical, lance e faixas de CPC e conversão, com código de acesso;
- links para o playbook e a planilha;
- os mesmos cuidados: CSP estrita, texto só via `textContent`, `examples.json` gerado pelo grafo com teste de drift.

## Divergência do padrão
Nenhuma.

## Consequências
- Impacto no plano: Fase 9.

## Critério de revisão
Se no teste de 30 segundos a pessoa não achar o semáforo, a tabela sobe para antes do texto de abertura.
