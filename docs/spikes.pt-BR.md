# Spikes de risco — Fase 1

> 🇧🇷 PT-BR · Data: 2026-11-19 · Base: [plano-implementacao.pt-BR.md](plano-implementacao.pt-BR.md), Fase 1

## Spike 1 — Formato da NOAA Storm Events

**Resposta: os dados servem. Mas furacão e vento costeiro vêm por zona, não por condado, e a narrativa de Cook precisa ser revista.**

**Evidência** (diretório de CSV da NCEI e arquivo de 2024, baixados em 2026-11-19):
- **Arquivos:** `StormEvents_details-ftp_v1.0_d<ANO>_c20261118.csv.gz`, de 2020 a 2025. O de 2025 pode estar incompleto (a página de download indica dados até out/2025), então os "últimos 5 anos completos" são **2020 a 2024**. O arquivo de 2024 tem 16 MB compactado.
- **Colunas úteis:**
  - `STATE_FIPS` + `CZ_FIPS` formam o FIPS do condado quando `CZ_TYPE == "C"`;
  - `EVENT_TYPE`; `MAGNITUDE` (diâmetro do granizo em polegadas);
  - `BEGIN_DATE_TIME`, `DAMAGE_PROPERTY`, `CZ_NAME`.
- **Granizo ≥ 1 polegada em 2024:** Cook (IL) **35** relatos; Dallas (TX) **20** (mais 8 abaixo de 1"); Pinellas (FL) nenhum relato por condado.
- **Achado 1:** furacão, tempestade tropical e vento costeiro são registrados com `CZ_TYPE == "Z"` (zona de previsão da NWS), não por condado. Para levar esses eventos ao condado, o ETL usa o arquivo oficial de correlação zona–condado da NWS (`bp<ddmmaa>.dbx`, separado por `|`, com o FIPS de 5 dígitos), versão vigente a confirmar no download.
- **Achado 2:** a narrativa "Cook com poucos eventos de clima" **não se sustenta**: Cook teve mais granizo que Dallas em 2024. A narrativa da tabela passa a ser decidida pelos dados de 5 anos na Fase 2 e pela conta do leilão (CPC de metrópole), não pelo clima.
- **Ressalva:** relatos de granizo não são eventos únicos; uma mesma tempestade gera vários relatos. O texto deve falar em "reports", nunca em "storms".

## Spike 2 — Census ACS por condado

**Resposta: sim. A API devolve todos os condados numa chamada.**

**Evidência** (`/data/2024/acs/acs5`, ACS 2020–2024, com a chave do Fabio, em 2026-11-19):
| Condado | Ano mediano de construção (B25035) | Domicílios com dono (B25003_002) | Valor mediano (B25077) |
|---|---|---|---|
| Dallas County, TX | 1983 | 498.911 de 982.737 domicílios | US$ 303.000 |
| Pinellas County, FL | 1977 | 297.912 | US$ 355.100 |
| Cook County, IL | 1961 | 1.212.570 | US$ 324.500 |

- Vacância (B25002): Dallas tem 82.228 de 1.064.965 unidades vazias.
- A chamada `for=county:*` devolveu **3.222 linhas** (os condados e equivalentes, incluindo Porto Rico).
- A chave é lida de `CENSUS_API_KEY`, só pelo ETL.

## Spike 3 — Fan-out com `Send` no `mypy --strict`

**Resposta: sim.**

**Evidência:** um grafo com `add_conditional_edges(START, fan_out, ["run_county"])`, em que `fan_out` devolve `list[Send]`, um redutor `Annotated[list[...], operator.add]` e um nó de comparação, rodou com 3 condados em paralelo e passou no `mypy --strict` sem supressões (langgraph 1.2.22).

## Spike 4 — Textos oficiais das regras

**Resposta: as regras de texto vêm do Fair Housing Act e do TCPA. A política do Google restringe segmentação, não texto.**

**Fair Housing Act, 42 U.S.C. § 3604(c), e HUD, 24 CFR § 100.75** (lidos em law.cornell.edu):
- É proibido anúncio de venda ou aluguel de moradia que indique preferência, limitação ou discriminação por **raça, cor, religião, sexo, deficiência, status familiar ou origem nacional**.
- O § 100.75(c)(1) inclui palavras, frases, fotos, símbolos e formulários; a lista de exemplos é "not limited to".
- O § 3604(e) proíbe induzir venda com afirmações sobre a entrada de pessoas de determinado grupo na vizinhança (*blockbusting*). É relevante para anúncios de "we buy houses".
- A lista federal **não** inclui idade nem estado civil; leis estaduais e municipais podem incluir, e ficam fora do MVP.

**TCPA, 47 CFR § 64.1200** (lido em law.cornell.edu):
- SMS conta como "call" ((a)(9)). Mensagem de marketing automatizada para celular exige **consentimento expresso por escrito** ((a)(2) e (f)(9)).
- "STOP", "QUIT", "END", "REVOKE", "OPT OUT", "CANCEL" e "UNSUBSCRIBE" revogam o consentimento ((a)(10)); a revogação deve ser honrada em até **10 dias úteis**.
- Identificar quem envia e oferecer contato ((d)(4)); horário de **8h às 21h** no fuso de quem recebe ((c)(1)).
- **Emenda nova:** FCC 26-67, publicada no Federal Register em 26/10/2026, **em vigor a partir de 25/11/2026**. Ela permite designar um método exclusivo de revogação, e segundo os escritórios consultados vale para mensagens **informativas**, não de telemarketing. Os SMS da demo são de marketing; a regra de opt-out por "STOP" continua. O texto vigente é relido na Fase 3, antes de virar configuração.

**Google Ads, "Housing in personalized advertising"** (nova página `support.google.com/adspolicy/answer/16701755`; a antiga deu 404):
- Nos EUA e no Canadá, anúncios de moradia **não podem segmentar** por gênero, idade, status parental, estado civil ou CEP.
- A política trata de **segmentação**, não de texto. A demo não configura segmentação (PRD, 3.2), então essa política vai para o README e o playbook como orientação, e as regras de texto vêm do Fair Housing Act.

**O que vira configuração na Fase 3:**
- **Fair Housing:** termos que indiquem preferência ou limitação pelas classes protegidas e afirmações de *blockbusting*.
- **TCPA:**
  - todo SMS identifica o remetente e traz instrução de opt-out com uma das palavras-chave;
  - o formulário traz o texto de consentimento por escrito;
  - os SMS da sequência respeitam a janela de 8h às 21h (metadado de horário sugerido).
- **Limites de caracteres** do Google Ads: títulos ≤ 30, descrições ≤ 90.

O checador não é aconselhamento jurídico, e a página e o README dizem isso.

## Decisões afetadas
- **ADR 006:** o ETL inclui o arquivo de correlação zona–condado da NWS; a janela é **2020–2024**.
- **PRD, seção 4:** a narrativa dos 3 condados é decidida na Fase 2, com os dados de 5 anos.
- **ADR 002:** o formulário ganha o texto de consentimento TCPA como item obrigatório.
