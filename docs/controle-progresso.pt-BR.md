# Controle de progresso — county-campaign-builder

> Documento vivo, atualizado ao fim de cada tarefa. Base: [plano-implementacao.pt-BR.md](plano-implementacao.pt-BR.md) · Data alvo: **2026-11-26** · Ponto de corte: **2026-11-22** (fim da Fase 4)
>
> Legenda: ✅ concluído · 🔄 em andamento · ⏳ pendente · ⚠️ bloqueado/risco · ✂️ cortado

## Visão geral

| Fase | Previsto | Status | Concluída em | Commit | Observação |
|------|----------|--------|--------------|--------|------------|
| 0 — Kickoff (PRD, ADRs, plano) | 19/11 | ✅ | 2026-11-19 | — | Portões 1, 2 e 3 aprovados |
| 1 — Esqueleto reaproveitado e spikes | 19/11 a 20/11 | 🔄 | | aguardando OK | Tudo pronto; falta o commit |
| 2 — ETL dos condados | 20/11 | ⏳ | | | |
| 3 — Contratos e domínio | 21/11 | ⏳ | | | |
| 4 — IA e grafo com fan-out | 21/11 a 22/11 | ⏳ | | | Checkpoint de corte |
| 5 — API e evals | 23/11 | ⏳ | | | |
| 6 — Página e playbook | 24/11 | ⏳ | | | |
| 7 — Esteira, container e deploy | 25/11 | ⏳ | | | |
| 8 — Documentação e publicação | 26/11 | ⏳ | | | |

## Spikes da Fase 1

| # | Pergunta | Resposta | Evidência | Decisão afetada |
|---|----------|----------|-----------|-----------------|
| 1 | Colunas reais do CSV de detalhes da NOAA (FIPS, tipo, magnitude do granizo) | ✅ com 2 achados | Furacão e vento costeiro vêm por zona (correlação NWS); Cook teve mais granizo que Dallas em 2024 | ADR 006, PRD 4 |
| 2 | Tabelas do ACS por condado (B25035, B25003, B25002, B25077) | ✅ | 3.222 condados numa chamada | ADR 006 |
| 3 | Fan-out com `Send` passa no `mypy --strict`? | ✅ | langgraph 1.2.22 | ADR 001 |
| 4 | Texto oficial de TCPA, Fair Housing e política de Housing do Google | ✅ | Google restringe segmentação, não texto; emenda TCPA em vigor em 25/11 (informativas) | ADR 002 |

## Medições (preencher com dado real, nunca estimativa)

| Métrica | Alvo | Medido | Data | Fonte |
|---------|------|--------|------|-------|
| Custo por condado ao vivo | ≤ US$ 0,30 | | | |
| Tempo por condado ao vivo | ≤ 90 s | | | |
| Tamanho da tabela de condados | ≤ 5 MB | | | |
| Ativos reprovados no fim (live) | ≤ 10% | | | |
| Nota G-Eval do copy | ≥ 0,7 | | | |

## Diário de bordo

| Data | Fase | O que aconteceu | Decisão / próximo passo |
|------|------|-----------------|-------------------------|
| 2026-11-19 | 0 | Kickoff a partir da vaga "Marketing AI & Automation Builder" (lead-gen imobiliário). O Fabio preferiu uma demo nova a pivotar o briefing-scout. PRD: 3 condados lado a lado, motivated seller + roofing, dados públicos estruturados, semáforo do leilão e número corrigido na primeira tela, revisão humana por pacote, playbook com planilha. Stack: motor do briefing-scout copiado, Anthropic (Haiku + Sonnet), fan-out com `Send`, ETL em Polars. | Fase 1; o Fabio vai pedir a chave do Census em api.census.gov/data/key_signup.html |
| 2026-11-19 | 1 | Esqueleto copiado do briefing-scout (Haiku): pacote `county_campaign_builder`, catraca verde (14 testes, 100%), workflows com `permissions`. Spikes: fan-out passa no mypy; Census com chave do Fabio devolve 3.222 condados; NOAA com 2 achados (furacão por zona e Cook com mais granizo que Dallas em 2024); textos oficiais lidos (FHA, HUD, TCPA e a emenda FCC 26-67, que vale a partir de 25/11 para mensagens informativas; política do Google é de segmentação). | Commit da Fase 1 aguardando o OK do Fabio; Fase 2 decide a narrativa com 5 anos de dados |
