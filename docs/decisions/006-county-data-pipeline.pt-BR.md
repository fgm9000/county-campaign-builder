# ADR 006 — Pipeline de dados dos condados

> 🇧🇷 PT-BR | 🇺🇸 [EN](006-county-data-pipeline.md) · Status: Aceita (Portão 2, 2026-11-19) · Data: 2026-11-19

## Contexto
Os fatos locais vêm de dados públicos estruturados (PRD, seção 7), e o modo ao vivo precisa funcionar em qualquer condado.

Consulta às fontes (2026-11-19):
- **NOAA Storm Events:** arquivos CSV anuais públicos (`StormEvents_details-ftp_v1.0_d<ANO>_c<DATA>.csv.gz`), sem chave. Cobertura de 1950 até out/2025 na página de download. As colunas de condado e de tamanho do granizo são conferidas no PDF de formato do próprio diretório na Fase 1.
- **Census ACS 5-year (2020–2024):** API em `/data/2024/acs/acs5`. **Toda consulta exige chave** (gratuita, pedida por e-mail). Tabelas candidatas: B25035 (ano mediano de construção), B25003 (posse), B25002 (vacância) e B25077 (valor mediano); a disponibilidade em nível de condado é conferida na Fase 1.

## Opções consideradas
| Opção | Prós | Contras |
|-------|------|---------|
| **A — Tabela pré-calculada de todos os condados** | O ao vivo roda em qualquer condado; sem API de dados em produção | Dados com data de corte; precisa de um ETL |
| B — Só os 3 condados | Mais rápido | O ao vivo fica limitado |
| C — APIs na hora | Sempre atualizado | Chave do Census em produção; CSV grande da NOAA a cada chamada |

## Decisão
Opção A:
- `scripts/build_county_table.py` (Polars) baixa os anos da NOAA, filtra eventos de condado (granizo ≥ 1 polegada, vento forte, furacão e tempestade tropical), agrega por FIPS nos últimos 5 anos completos e junta com o ACS;
- a saída é `data/counties.parquet` (e uma cópia `.json` para o modelo falso, se necessário), com as colunas, a data de corte e a fonte de cada campo;
- a chave do Census é usada só pelo script, lida de variável de ambiente, nunca no repositório nem em produção;
- o runtime só lê a tabela.

## Divergência do padrão
O Padrão Mestre não prevê ETL. Entra um script com teste da lógica de agregação (sobre amostras pequenas versionadas) e a tabela gerada versionada.

## Consequências
- Positivas: evidência de engenharia de dados (Polars); o verificador numérico tem uma fonte fixa e auditável.
- Negativas: os dados envelhecem; o README traz a data de corte.
- Impacto no plano: Fase 2.

## Critério de revisão
Se o arquivo passar de 5 MB ou o ETL exigir dados com licença restrita, reduzir as colunas ou os anos.
