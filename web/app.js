/**
 * County Campaign Builder — Static Web Playground
 *
 * Pure ES2020 module: zero external CDNs, zero bundlers, zero innerHTML.
 * All dynamic values from JSON or SSE are rendered exclusively via textContent.
 */

const LANG_STORAGE_KEY = "ccb-lang";
const DEFAULT_LANG = "en";
const LIVE_TIMEOUT_MS = 120_000;
const COPIED_FEEDBACK_MS = 2_000;
const STREAM_PATH = "/v1/campaigns/stream";

const LIMITS = {
  headline: 30,
  description: 90,
  sms: 160,
};

const BRAND_BY_VERTICAL = {
  motivated_seller: "Example Home Buyers",
  roofing: "Example Roofing Co.",
};

const OPT_OUT_KEYWORDS = ["STOP", "QUIT", "END", "REVOKE", "OPT OUT", "CANCEL", "UNSUBSCRIBE"];

const PROGRESS_STAGES = [
  "loading_data",
  "interpreting_triggers",
  "verifying_numbers",
  "drafting_copy",
  "checking_compliance",
  "computing_economics",
];

const MAIN_TAB_IDS = ["tabCounty48113", "tabCounty12103", "tabCounty17031", "tabLive"];

const I18N = {
  en: {
    moreProjects: "← More projects on GitHub",
    zeroCostBadge: "Pre-computed mode: zero API cost",
    subtitle: "Verified local facts · Deterministic auction math · Compliant ad & intake copy",
    linkExcel: "Download Excel Model (auction-math.xlsx)",
    linkPlaybook: "Non-Code Playbook (README.md)",
    linkRepo: "GitHub Repo ↗",
    heroBadgeArchitecture: "Production AI Engine Architecture",
    heroBadgeStack: "LangGraph + Parquet + Census ACS + NOAA",
    heroTitle: "Why Pure LLMs Fail in Paid Acquisition — And How Code Makes Them Production-Ready",
    heroLead: "In high-stakes paid advertising, pure LLMs hallucinate financial metrics, blow past ad character limits, and violate regulatory disclosures. This demo showcases a deterministic, audit-first orchestration system: Code owns the math, data integrity, and compliance; AI owns copy creativity and audience persuasion.",
    pillar1Title: "Anti-Hallucination Firewall",
    pillar1Text: "Zero tolerance for invented numbers. LLM claims are cross-checked against local Parquet Census ACS tables. Mismatches are automatically reconciled and logged to an audit trail.",
    pillar2Title: "Deterministic Auction Math",
    pillar2Text: "Unit economics (target CPL, max CPC threshold, traffic-light go/no-go verdicts) are 100% computed in Python with float precision — never delegated to a probabilistic model.",
    pillar3Title: "Audience-Tailored Copywriting",
    pillar3Text: "Strict separation between B2B intelligence (market tenure, equity) and B2C creative. Landing pages and SMS speak 100% to motivated home sellers (as-is sale, zero fees, 7-14 day close).",
    pillar4Title: "Deterministic Compliance",
    pillar4Text: "Deterministic regex engine enforces Fair Housing Act rules, TCPA SMS disclosures, Google Ads character counts (30/90), and qualification question logic with 100% test coverage.",
    thirtySecondHeading: "30-Second Overview: Auction Math and Fact Verification",
    auctionEyebrow: "Deterministic Code Math (Never LLM)",
    auctionTitle: "Multi-County Auction Math",
    recommendedPrefix: "Recommended:",
    colCounty: "County",
    colVerdict: "Verdict",
    colBid: "Bid",
    colCpl: "CPL Range",
    colMaxCpc: "Max CPC",
    colMath: "Auction Math Explanation",
    loadingExamples: "Loading county auction math…",
    assumptionsNote:
      "Assumptions note: CPC and landing-page CVR ranges in this pre-computed benchmark are illustrative operator inputs (Dallas $2–$4 CPC / 5–10% CVR; Pinellas $4.50–$9 CPC / 6–10% CVR; Cook $11–$15 CPC / 5–8% CVR), not live ad-platform market data.",
    correctionEyebrow: "Automated Fact Audit",
    correctionTitle: "Code Caught AI Hallucination",
    correctedAuditedBadge: "Corrected & Audited",
    llmGeneratedLabel: "LLM Generated",
    officialSourceLabel: "Official Source",
    divisionTitle: "Explicit Division of Labor",
    roleAi: "AI (LLM)",
    roleAiDesc: "Interprets local triggers; drafts questions, RSA ads, landing page, SMS, and emails.",
    roleCode: "Code",
    roleCodeDesc:
      "Verifies numbers vs. NOAA/Census; computes CPL & max CPC; enforces char limits, TCPA & Fair Housing.",
    roleHuman: "Human",
    roleHumanDesc: "Approves offer terms, closing promises, quiet hours, and local positioning.",
    explorerHeading: "Campaign Package Explorer & Live Runner",
    explorerSubtitle:
      "Inspect every audited asset per county or run the full pipeline live on any of 3,222 U.S. counties.",
    tabDallas: "Dallas County, TX",
    tabPinellas: "Pinellas County, FL",
    tabCook: "Cook County, IL",
    tabLive: "Live County Run",
    copyMarkdown: "Copy as Markdown",
    copiedMarkdown: "Copied!",
    copyFailed: "Copy failed",
    secAll: "All Sections",
    secEconomics: "Unit Economics",
    secFacts: "Verified Facts",
    secQuestions: "Qualification Questions",
    secAds: "Responsive Search Ads",
    secLanding: "Landing Page Top",
    secFollowup: "Follow-Up Sequences",
    secReview: "Human Review Checklist",
    verdicts: { green: "GREEN", yellow: "YELLOW", red: "RED" },
    factStatuses: { verified: "Verified", corrected: "Corrected", unverified: "Unverified" },
    assetStatuses: {
      approved: "Approved",
      rejected: "Rejected",
      regenerated: "Regenerated",
      needs_human_review: "Needs Review",
      missing: "Missing",
    },
    verticalLabels: {
      motivated_seller: "Motivated Seller (Cash Offer)",
      roofing: "Roof Replacement",
    },
    topicLabels: {
      timeline: "Timeline",
      property_condition: "Property Condition",
      listed_with_agent: "Listed With Agent",
      decision_maker: "Decision Maker",
      reason_for_selling: "Reason For Selling",
      homeowner: "Homeowner",
      roof_age: "Roof Age",
      damage_type: "Damage Type",
      replacement_vs_repair: "Replacement vs. Repair",
      insurance_claim: "Insurance Claim",
    },
    unitEconomicsTitle: "Unit Economics",
    metricBid: "Lead Bid",
    metricCplBest: "Best-Case CPL",
    metricCplWorst: "Worst-Case CPL",
    metricMaxCpc: "Max Viable CPC",
    assumptionsLine: "Operator inputs: CPC {cpcMin}–{cpcMax} · Landing CVR {cvrMin}–{cvrMax}",
    factsTitle: "County Intelligence & Audited Facts (B2B Strategy)",
    factsSubtitle: "Official U.S. Census Bureau & NOAA demographic/climate data used by media buyers and acquisition teams to evaluate equity, repair risks, and calibrate local ad spend.",
    sourceLabel: "Source:",
    fieldLabel: "Field:",
    valueLabel: "Verified value:",
    auditDelta: "Audited correction: LLM output {llm} → Official source {source}",
    questionsTitle: "Qualification Questions",
    whyLabel: "Why it matters:",
    adsTitle: "Responsive Search Ads (Google Ads)",
    headlinesHeading: "Headlines (max 30 chars)",
    descriptionsHeading: "Descriptions (max 90 chars)",
    charsUnit: "chars",
    landingTitle: "Landing Page Preview (Homeowner Above-the-Fold)",
    ctaPreviewLabel: "CTA Button:",
    tcpaBadge: "TCPA Consent Disclosure",
    followupTitle: "Follow-Up Sequences",
    smsHeading: "Speed-to-Lead SMS (max 160 chars)",
    emailHeading: "Follow-Up Emails",
    smsLabel: "SMS #{n}",
    emailLabel: "Email #{n}",
    subjectLabel: "Subject:",
    brandBadge: "Brand: {brand}",
    brandMissingBadge: "Missing brand ID",
    optOutBadge: "Opt-out: {keyword}",
    optOutMissingBadge: "Missing opt-out",
    reviewTitle: "Human Review Checklist",
    reviewAlertTitle: "{n} Item(s) Flagged for Human Sign-Off Before Launch",
    reviewAlertDesc:
      "The automated compliance engine detected unverified promises or offer terms that require human operator approval. Review the highlighted yellow items below:",
    sectionFlaggedBadge: "⚠️ {n} flagged for review",
    inlineReviewBadge: "⚠️ Human Sign-Off Required",
    needsReviewPill: "Needs Sign-Off",
    headlineWord: "Headline",
    descriptionWord: "Description",
    lpHeadlineWord: "Landing Page Headline",
    lpSubheadlineWord: "Landing Page Subheadline",
    reviewFlaggedCount: "{n} item(s) flagged",
    reviewCleanBadge: "0 claim triggers fired",
    reviewEmptyMsg:
      "No unverified promise triggers (closing guarantees, offer price claims, or insurance-coverage claims) were detected in this package.",
    reviewStandingNote:
      "Standing human sign-off required before launch: verify TCPA quiet hours (8 a.m.–9 p.m. recipient local time) and confirm final buyer offer terms.",
    ruleLabel: "Rule:",
    liveFormTitle: "Run Live County Pipeline",
    liveFormSubtitle:
      "Streams 6 real-time SSE stages from /v1/campaigns/stream using official NOAA + Census aggregates.",
    fFips: "County FIPS (5 digits)",
    fFipsHint: "e.g. 48113 (Dallas), 12103 (Pinellas), 17031 (Cook), or any US county",
    fVertical: "Vertical",
    vMotivatedSeller: "Motivated Seller (Cash Offer)",
    vRoofing: "Roofing (Roof Replacement)",
    fBid: "Bid per Lead ($ USD)",
    fCpcMin: "Min CPC ($ USD)",
    fCpcMax: "Max CPC ($ USD)",
    fCvrMin: "Min Landing CVR (%)",
    fCvrHint: "Entered as % (e.g. 5.0 = 5.0% CVR)",
    fCvrMax: "Max Landing CVR (%)",
    fAccessCode: "Access Code",
    fAccessHint: "Held in memory for this tab only; never saved.",
    liveRunBtn: "Run Live Campaign",
    liveRunningBtn: "Running Pipeline…",
    progressTitle: "Live Pipeline Progress",
    fallbackExamplesBtn: "Explore Pre-Computed Examples",
    stages: {
      loading_data: "1. Loading County Data",
      interpreting_triggers: "2. Interpreting Triggers",
      verifying_numbers: "3. Verifying Numbers",
      drafting_copy: "4. Drafting Copy",
      checking_compliance: "5. Checking Compliance",
      computing_economics: "6. Computing Unit Economics",
    },
    apiUnconfiguredNotice:
      "Live API endpoint is not configured in web/config.json (apiUrl is empty). Static pre-computed counties work offline; clicking Run Live Campaign will try same-origin /v1/campaigns/stream or guide you back to the examples.",
    errExamplesLoad:
      "Could not load web/examples.json. If opening via file://, serve the web/ directory over HTTP (e.g. python -m http.server).",
    errInvalidForm: "Check your inputs: FIPS must be 5 digits, Bid > 0, Min <= Max for CPC and CVR (0.1%–100%).",
    errUnauthorized: "Invalid or missing access code (HTTP 401). Please verify your code and try again.",
    errRateLimited: "Rate limit exceeded (HTTP 429). Please retry in {seconds}s.",
    errRateLimitedNoWait: "Rate limit exceeded (HTTP 429). Please wait before retrying.",
    errValidation: "Validation error (HTTP 422): {detail}",
    errApiOffline:
      "Live API is offline or unreachable right now. You can still inspect all three pre-computed county packages.",
    errServer: "API returned an error (HTTP {status}). You can inspect the pre-computed county examples instead.",
    errTimeout: "Live campaign request timed out. Please try again or inspect pre-computed examples.",
    errStreamFailed: "Live pipeline encountered an error while generating this county package.",
    errBadStream: "Unexpected response from live stream endpoint.",
    liveReadyAnnounce: "Live campaign package ready for {county}.",
    footerCopy:
      "County Campaign Builder · Automated compliance checks are not legal advice; a human operator reviews every package before launch.",
    footerLicense: "PolyForm Noncommercial 1.0.0",
  },
  pt: {
    moreProjects: "← Mais projetos no GitHub",
    zeroCostBadge: "Modo pré-computado: custo zero de API",
    subtitle: "Fatos locais verificados · Conta do leilão determinística · Copy e compliance",
    linkExcel: "Baixar Planilha Excel (auction-math.xlsx)",
    linkPlaybook: "Playbook Sem Código (README.md)",
    linkRepo: "Repositório GitHub ↗",
    heroBadgeArchitecture: "Arquitetura de Motor de IA em Produção",
    heroBadgeStack: "LangGraph + Parquet + Censo ACS + NOAA",
    heroTitle: "Por que LLMs Puros Falham em Tráfego Pago — E Como Código os Torna Confiáveis",
    heroLead: "Em tráfego pago de alto risco, LLMs puros inventam métricas financeiras, estouram limites de caracteres de anúncios e violam leis de compliance. Esta demo apresenta uma arquitetura determinística de auditoria contínua: Código domina a matemática, integridade de dados e conformidade; IA domina a criatividade e persuasão das mensagens.",
    pillar1Title: "Firewall Anti-Alucinação",
    pillar1Text: "Tolerância zero a números inventados. Afirmações do LLM são auditadas contra tabelas Parquet oficiais do Censo ACS. Divergências são retificadas automaticamente com trilha de auditoria.",
    pillar2Title: "Matemática de Leilão Determinística",
    pillar2Text: "Unit economics (CPL alvo, teto de CPC, semáforo go/no-go) são calculados 100% em Python com precisão de ponto flutuante — nunca delegados a modelos probabilísticos.",
    pillar3Title: "Copywriting Focado no Público Certo",
    pillar3Text: "Separação estrita entre inteligência de mercado B2B e peças B2C. Landing pages e SMS falam 100% com proprietários que querem vender (sem reformas, zero taxas, fechamento em 7-14 dias).",
    pillar4Title: "Conformidade Regulatória por Código",
    pillar4Text: "Mecanismo regex determinístico garante conformidade com Fair Housing Act, TCPA para SMS, limites de caracteres do Google Ads (30/90) e qualificação com 100% de cobertura de testes.",
    thirtySecondHeading: "Visão em 30 Segundos: Conta do Leilão e Verificação de Fatos",
    auctionEyebrow: "Matemática Determinística em Código (Nunca LLM)",
    auctionTitle: "Conta do Leilão Multi-Condado",
    recommendedPrefix: "Recomendado:",
    colCounty: "Condado",
    colVerdict: "Semáforo",
    colBid: "Lance",
    colCpl: "Faixa de CPL",
    colMaxCpc: "CPC Máx.",
    colMath: "Explicação da Conta",
    loadingExamples: "Carregando conta do leilão…",
    assumptionsNote:
      "Nota sobre premissas: as faixas de CPC e conversão (CVR) neste benchmark pré-computado são entradas ilustrativas do operador (Dallas $2–$4 CPC / 5–10% CVR; Pinellas $4.50–$9 CPC / 6–10% CVR; Cook $11–$15 CPC / 5–8% CVR), não dados ao vivo da plataforma de anúncios.",
    correctionEyebrow: "Auditoria Automática de Fatos",
    correctionTitle: "Código Corrigiu Alucinação da IA",
    correctedAuditedBadge: "Corrigido e Auditado",
    llmGeneratedLabel: "Gerado pelo LLM",
    officialSourceLabel: "Fonte Oficial",
    divisionTitle: "Divisão Explícita de Trabalho",
    roleAi: "IA (LLM)",
    roleAiDesc: "Interpreta gatilhos locais; redige perguntas, anúncios RSA, landing page, SMS e e-mails.",
    roleCode: "Código",
    roleCodeDesc:
      "Confere números contra NOAA/Census; calcula CPL e CPC máx.; aplica limites, TCPA e Fair Housing.",
    roleHuman: "Humano",
    roleHumanDesc: "Aprova condições de oferta, prazos de fechamento, quiet hours e tom local.",
    explorerHeading: "Explorador de Pacotes e Execução ao Vivo",
    explorerSubtitle:
      "Inspecione cada ativo auditado por condado ou rode o pipeline ao vivo em qualquer um dos 3.222 condados dos EUA.",
    tabDallas: "Dallas County, TX",
    tabPinellas: "Pinellas County, FL",
    tabCook: "Cook County, IL",
    tabLive: "Rodada ao Vivo",
    copyMarkdown: "Copiar como Markdown",
    copiedMarkdown: "Copiado!",
    copyFailed: "Falha ao copiar",
    secAll: "Todas as Seções",
    secEconomics: "Economia Unitária",
    secFacts: "Fatos Verificados",
    secQuestions: "Perguntas de Qualificação",
    secAds: "Anúncios RSA",
    secLanding: "Topo da Landing Page",
    secFollowup: "Sequências de Follow-Up",
    secReview: "Revisão Humana",
    verdicts: { green: "VERDE", yellow: "AMARELO", red: "VERMELHO" },
    factStatuses: { verified: "Verificado", corrected: "Corrigido", unverified: "Não verificado" },
    assetStatuses: {
      approved: "Aprovado",
      rejected: "Reprovado",
      regenerated: "Regenerado",
      needs_human_review: "Revisão Humana",
      missing: "Ausente",
    },
    verticalLabels: {
      motivated_seller: "Motivated Seller (Oferta em Dinheiro)",
      roofing: "Roof Replacement (Troca de Telhado)",
    },
    topicLabels: {
      timeline: "Prazo",
      property_condition: "Condição do Imóvel",
      listed_with_agent: "Listado com Corretor",
      decision_maker: "Tomador de Decisão",
      reason_for_selling: "Motivo da Venda",
      homeowner: "Proprietário",
      roof_age: "Idade do Telhado",
      damage_type: "Tipo de Dano",
      replacement_vs_repair: "Troca vs. Reparo",
      insurance_claim: "Acionamento de Seguro",
    },
    unitEconomicsTitle: "Economia Unitária",
    metricBid: "Lance por Lead",
    metricCplBest: "Melhor CPL",
    metricCplWorst: "Pior CPL",
    metricMaxCpc: "CPC Máx. Viável",
    assumptionsLine: "Premissas do operador: CPC {cpcMin}–{cpcMax} · CVR da LP {cvrMin}–{cvrMax}",
    factsTitle: "Dossiê de Mercado & Fatos Auditados (Estratégia B2B)",
    factsSubtitle: "Métricas oficiais do Censo dos EUA e NOAA utilizadas pela equipe de aquisição imobiliária para analisar o mercado do condado e calibrar lances de leilão.",
    sourceLabel: "Fonte:",
    fieldLabel: "Campo:",
    valueLabel: "Valor verificado:",
    auditDelta: "Correção auditada: LLM gerou {llm} → Fonte oficial {source}",
    questionsTitle: "Perguntas de Qualificação",
    whyLabel: "Por que importa:",
    adsTitle: "Anúncios Responsivos de Pesquisa (Google Ads)",
    headlinesHeading: "Títulos (máx. 30 caracteres)",
    descriptionsHeading: "Descrições (máx. 90 caracteres)",
    charsUnit: "caract.",
    landingTitle: "Prévia da Landing Page (Visão do Proprietário)",
    ctaPreviewLabel: "Botão CTA:",
    tcpaBadge: "Declaração de Consentimento TCPA",
    followupTitle: "Sequências de Follow-Up",
    smsHeading: "SMS Speed-to-Lead (máx. 160 caracteres)",
    emailHeading: "E-mails de Follow-Up",
    smsLabel: "SMS #{n}",
    emailLabel: "E-mail #{n}",
    subjectLabel: "Assunto:",
    brandBadge: "Marca: {brand}",
    brandMissingBadge: "Marca ausente",
    optOutBadge: "Opt-out: {keyword}",
    optOutMissingBadge: "Opt-out ausente",
    reviewTitle: "Checklist de Revisão Humana",
    reviewAlertTitle: "{n} Item(ns) Marcado(s) para Aprovação Humana Antes de Publicar",
    reviewAlertDesc:
      "O mecanismo de conformidade detectou promessas ou condições de oferta que exigem confirmação do operador humano. Confira os itens destacados em amarelo abaixo:",
    sectionFlaggedBadge: "⚠️ {n} marcado(s) para revisão",
    inlineReviewBadge: "⚠️ Aprovação Humana Obrigatória",
    needsReviewPill: "Requer Aprovação",
    headlineWord: "Título",
    descriptionWord: "Descrição",
    lpHeadlineWord: "Título da Landing Page",
    lpSubheadlineWord: "Subtítulo da Landing Page",
    reviewFlaggedCount: "{n} item(ns) marcado(s)",
    reviewCleanBadge: "0 gatilhos de promessa disparados",
    reviewEmptyMsg:
      "Nenhum gatilho de promessa não verificável (garantia de fechamento, promessa de preço ou cobertura de seguro) foi detectado neste pacote.",
    reviewStandingNote:
      "Aprovação humana obrigatória antes de publicar: validar horário permitido pelo TCPA (8h–21h no fuso local do lead) e confirmar condições finais do comprador.",
    ruleLabel: "Regra:",
    liveFormTitle: "Rodar Pipeline ao Vivo por Condado",
    liveFormSubtitle:
      "Transmite 6 etapas SSE em tempo real de /v1/campaigns/stream usando agregados oficiais NOAA + Census.",
    fFips: "FIPS do Condado (5 dígitos)",
    fFipsHint: "ex.: 48113 (Dallas), 12103 (Pinellas), 17031 (Cook) ou qualquer condado dos EUA",
    fVertical: "Vertical",
    vMotivatedSeller: "Motivated Seller (Oferta em Dinheiro)",
    vRoofing: "Roofing (Troca de Telhado)",
    fBid: "Lance por Lead ($ USD)",
    fCpcMin: "CPC Mínimo ($ USD)",
    fCpcMax: "CPC Máximo ($ USD)",
    fCvrMin: "CVR Mínima da LP (%)",
    fCvrHint: "Informe em % (ex.: 5.0 = 5.0% de conversão)",
    fCvrMax: "CVR Máxima da LP (%)",
    fAccessCode: "Código de Acesso",
    fAccessHint: "Mantido apenas em memória nesta aba; nunca salvo.",
    liveRunBtn: "Rodar Campanha ao Vivo",
    liveRunningBtn: "Executando Pipeline…",
    progressTitle: "Progresso do Pipeline ao Vivo",
    fallbackExamplesBtn: "Explorar Exemplos Pré-Computados",
    stages: {
      loading_data: "1. Carregando Dados do Condado",
      interpreting_triggers: "2. Interpretando Gatilhos",
      verifying_numbers: "3. Verificando Números",
      drafting_copy: "4. Redigindo Copy",
      checking_compliance: "5. Checando Compliance",
      computing_economics: "6. Calculando Economia Unitária",
    },
    apiUnconfiguredNotice:
      "A URL da API ao vivo não está configurada em web/config.json (apiUrl está vazio). Os condados pré-computados funcionam offline; clicar em Rodar Campanha ao Vivo tentará /v1/campaigns/stream na mesma origem ou oferecerá retorno aos exemplos.",
    errExamplesLoad:
      "Não foi possível carregar web/examples.json. Se abriu via file://, sirva a pasta web/ via HTTP (ex.: python -m http.server).",
    errInvalidForm:
      "Verifique os campos: FIPS deve ter 5 dígitos, Lance > 0, Mín <= Máx para CPC e CVR (0.1%–100%).",
    errUnauthorized: "Código de acesso inválido ou ausente (HTTP 401). Verifique o código e tente novamente.",
    errRateLimited: "Limite de requisições atingido (HTTP 429). Tente novamente em {seconds}s.",
    errRateLimitedNoWait: "Limite de requisições atingido (HTTP 429). Aguarde antes de tentar novamente.",
    errValidation: "Erro de validação (HTTP 422): {detail}",
    errApiOffline:
      "A API ao vivo está offline ou inacessível no momento. Você pode continuar explorando os três pacotes pré-computados.",
    errServer: "A API retornou erro (HTTP {status}). Explore os exemplos pré-computados enquanto isso.",
    errTimeout: "A requisição ao vivo expirou. Tente novamente ou explore os exemplos pré-computados.",
    errStreamFailed: "O pipeline ao vivo encontrou um erro ao gerar o pacote deste condado.",
    errBadStream: "Resposta inesperada do endpoint de streaming ao vivo.",
    liveReadyAnnounce: "Pacote ao vivo pronto para {county}.",
    footerCopy:
      "County Campaign Builder · Checagens automáticas de compliance não constituem aconselhamento jurídico; um operador humano revisa cada pacote antes do uso.",
    footerLicense: "PolyForm Noncommercial 1.0.0",
  },
};

const state = {
  lang: DEFAULT_LANG,
  apiUrl: "",
  examples: null,
  activeTab: "tabCounty48113",
  activeCountyFips: "48113",
  activeSection: "all",
  liveCampaign: null,
  liveInputs: null,
  liveRunId: 0,
  stageStates: {},
};

function $(id) {
  return document.getElementById(id);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function t(key, vars = {}) {
  const dict = I18N[state.lang] || I18N.en;
  let value = dict[key];
  if (value === undefined) value = I18N.en[key] ?? key;
  if (typeof value !== "string") return key;
  return value.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? String(vars[k]) : `{${k}}`));
}

function tNested(group, key, fallback) {
  const dict = I18N[state.lang] || I18N.en;
  const bucket = dict[group] || I18N.en[group] || {};
  return bucket[key] ?? fallback ?? key;
}

function fmtUsd(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "$0.00";
  return `$${num.toFixed(2)}`;
}

function fmtPct(decimalValue) {
  const num = Number(decimalValue);
  if (!Number.isFinite(num)) return "0.0%";
  return `${(num * 100).toFixed(1)}%`;
}

function formatTopicLabel(topic) {
  if (!topic) return "General";
  const mapped = tNested("topicLabels", topic, null);
  if (mapped) return mapped;
  return String(topic)
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function verdictPillClass(verdict) {
  if (verdict === "green") return "pill pill-green";
  if (verdict === "yellow") return "pill pill-yellow";
  return "pill pill-red";
}

function announce(message) {
  const node = $("liveAnnouncer");
  if (node) node.textContent = message;
}

/* ------------------------------------------------------------------------------ i18n */

function initialLang() {
  try {
    const saved = window.localStorage.getItem(LANG_STORAGE_KEY);
    if (saved === "en" || saved === "pt") return saved;
  } catch {
    // Ignore storage access errors in restricted contexts.
  }
  return DEFAULT_LANG;
}

function setLang(lang) {
  state.lang = lang === "pt" ? "pt" : "en";
  document.documentElement.lang = state.lang;
  try {
    window.localStorage.setItem(LANG_STORAGE_KEY, state.lang);
  } catch {
    // Ignore storage access errors.
  }
  $("langEn").classList.toggle("is-active", state.lang === "en");
  $("langEn").setAttribute("aria-pressed", String(state.lang === "en"));
  $("langPt").classList.toggle("is-active", state.lang === "pt");
  $("langPt").setAttribute("aria-pressed", String(state.lang === "pt"));
  applyStaticI18n();
  renderAllDynamic();
}

function applyStaticI18n() {
  for (const node of document.querySelectorAll("[data-i18n]")) {
    const key = node.getAttribute("data-i18n");
    if (key) node.textContent = t(key);
  }
  renderLiveApiNotice();
}

/* ------------------------------------------------------------------------------ 30-Second Rule */

function getCampaignsList() {
  if (!state.examples) return [];
  if (Array.isArray(state.examples.campaigns) && state.examples.campaigns.length > 0) {
    return state.examples.campaigns;
  }
  if (state.examples.comparison && Array.isArray(state.examples.comparison.campaigns)) {
    return state.examples.comparison.campaigns;
  }
  return [];
}

function renderAuctionMathTable() {
  const tbody = $("auctionTableBody");
  const summaryEl = $("comparisonSummary");
  const recommendedPill = $("recommendedPill");
  clearNode(tbody);

  const campaigns = getCampaignsList();
  if (campaigns.length === 0) {
    const row = el("tr");
    const cell = el("td", "table-loading", t("loadingExamples"));
    cell.colSpan = 6;
    row.appendChild(cell);
    tbody.appendChild(row);
    summaryEl.hidden = true;
    recommendedPill.hidden = true;
    return;
  }

  for (const campaign of campaigns) {
    const econ = campaign.unit_economics || {};
    const verdict = econ.verdict || "red";
    const row = el("tr", verdict === "red" ? "auction-row auction-row-red" : "auction-row");

    // County + FIPS clickable cell
    const countyTd = el("td");
    const countyBtn = el("button", "county-cell-btn", campaign.county_name);
    countyBtn.type = "button";
    countyBtn.addEventListener("click", () => {
      selectCountyFromTable(campaign.county_fips);
    });
    const fipsSpan = el("span", "county-fips-sub", `FIPS ${campaign.county_fips}`);
    countyTd.append(countyBtn, fipsSpan);
    row.appendChild(countyTd);

    // Verdict pill
    const verdictTd = el("td");
    verdictTd.appendChild(el("span", verdictPillClass(verdict), tNested("verdicts", verdict, verdict.toUpperCase())));
    row.appendChild(verdictTd);

    // Bid
    row.appendChild(el("td", "mono-num", fmtUsd(econ.bid_per_lead_usd)));

    // CPL range
    const cplRange = `${fmtUsd(econ.cpl_best_usd)} – ${fmtUsd(econ.cpl_worst_usd)}`;
    row.appendChild(el("td", "mono-num", cplRange));

    // Max CPC
    row.appendChild(el("td", "mono-num", fmtUsd(econ.max_cpc_usd)));

    // Explicit math explanation
    const explainClass = verdict === "red" ? "math-explain-cell math-explain-red" : "math-explain-cell";
    row.appendChild(el("td", explainClass, econ.explanation || ""));

    row.addEventListener("click", (ev) => {
      if (ev.target !== countyBtn) selectCountyFromTable(campaign.county_fips);
    });

    tbody.appendChild(row);
  }

  const comparison = state.examples?.comparison;
  if (comparison?.recommended_county_fips) {
    const rec = campaigns.find((c) => c.county_fips === comparison.recommended_county_fips);
    if (rec) {
      recommendedPill.textContent = `${t("recommendedPrefix")} ${rec.county_name}`;
      recommendedPill.hidden = false;
    }
  }
  if (comparison?.summary) {
    summaryEl.textContent = comparison.summary;
    summaryEl.hidden = false;
  }
}

function renderCorrectionCallout() {
  const campaigns = getCampaignsList();
  let targetCampaign = null;
  let targetCorrection = null;

  for (const camp of campaigns) {
    if (Array.isArray(camp.corrections) && camp.corrections.length > 0) {
      targetCampaign = camp;
      targetCorrection = camp.corrections[0];
      break;
    }
  }

  if (!targetCampaign || !targetCorrection) return;

  const matchingFact = Array.isArray(targetCampaign.facts)
    ? targetCampaign.facts.find((f) => f.field === targetCorrection.field)
    : null;

  const isCurrency = targetCorrection.field === "median_home_value_usd";
  const llmDisplay = isCurrency
    ? `$${Number(targetCorrection.llm_value).toLocaleString("en-US")}`
    : String(targetCorrection.llm_value);
  const srcDisplay = isCurrency
    ? `$${Number(targetCorrection.source_value).toLocaleString("en-US")}`
    : String(targetCorrection.source_value);

  const defaultSource = isCurrency
    ? "U.S. Census Bureau ACS (Table B25077)"
    : "NOAA Storm Events 2020-2024";

  $("correctionCounty").textContent = `${targetCampaign.county_name} (FIPS ${targetCampaign.county_fips})`;
  $("correctionHeadline").textContent =
    state.lang === "pt"
      ? (isCurrency
          ? `LLM gerou valor mediano de ${llmDisplay} → Fonte oficial do Census é ${srcDisplay}: corrigido e auditado`
          : `LLM gerou ${targetCorrection.llm_value} para ${targetCorrection.field} → Fonte oficial é ${targetCorrection.source_value}: corrigido e auditado`)
      : (isCurrency
          ? `LLM generated ${llmDisplay} median home value → Census official source is ${srcDisplay}: corrected and audited`
          : `LLM generated ${targetCorrection.llm_value} for ${targetCorrection.field} → Official source is ${targetCorrection.source_value}: corrected and audited`);
  $("correctionLlmVal").textContent = llmDisplay;
  $("correctionFieldLabel").textContent = isCurrency
    ? (state.lang === "pt" ? "Valor Mediano (Censo B25077)" : "Median Home Value (Census B25077)")
    : targetCorrection.field;
  $("correctionSourceVal").textContent = srcDisplay;
  $("correctionSourceName").textContent = matchingFact?.source || defaultSource;
  $("correctionReason").textContent = targetCorrection.reason || "";
}

function selectCountyFromTable(fips) {
  const tabId = `tabCounty${fips}`;
  if ($(tabId)) {
    selectMainTab(tabId, false);
    const explorer = $("explorerSection");
    if (explorer && typeof explorer.scrollIntoView === "function") {
      explorer.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
}

/* ------------------------------------------------------------------------------ Campaign Package Viewer */

function statusBadgeClass(status) {
  if (status === "approved" || status === "verified") return "badge badge-green";
  if (status === "corrected" || status === "regenerated" || status === "needs_human_review") {
    return "badge badge-yellow";
  }
  if (status === "rejected" || status === "unverified" || status === "missing") {
    return "badge badge-red";
  }
  return "badge badge-neutral";
}

function renderUnitEconomicsSection(campaign, inputAssumptions) {
  const section = el("section", "pkg-section");
  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("unitEconomicsTitle")));

  const econ = campaign.unit_economics || {};
  const verdict = econ.verdict || "red";
  head.appendChild(el("span", verdictPillClass(verdict), tNested("verdicts", verdict, verdict.toUpperCase())));
  section.appendChild(head);

  const grid = el("div", "econ-grid");
  const metrics = [
    [t("metricBid"), fmtUsd(econ.bid_per_lead_usd)],
    [t("metricCplBest"), fmtUsd(econ.cpl_best_usd)],
    [t("metricCplWorst"), fmtUsd(econ.cpl_worst_usd)],
    [t("metricMaxCpc"), fmtUsd(econ.max_cpc_usd)],
  ];
  for (const [label, value] of metrics) {
    const box = el("div", "metric-box");
    box.append(el("span", "metric-label", label), el("span", "metric-value", value));
    grid.appendChild(box);
  }
  section.appendChild(grid);

  if (inputAssumptions?.cpc_usd && inputAssumptions?.landing_cvr) {
    const line = t("assumptionsLine", {
      cpcMin: fmtUsd(inputAssumptions.cpc_usd.min),
      cpcMax: fmtUsd(inputAssumptions.cpc_usd.max),
      cvrMin: fmtPct(inputAssumptions.landing_cvr.min),
      cvrMax: fmtPct(inputAssumptions.landing_cvr.max),
    });
    section.appendChild(el("p", "sub-card-meta", line));
  }

  const explainClass = `econ-explanation verdict-${verdict}`;
  const explainEl = el("p", explainClass, econ.explanation || "");
  explainEl.style.marginTop = "10px";
  section.appendChild(explainEl);

  return section;
}

const METRIC_INSIGHTS = {
  median_home_value_usd: {
    nameEn: "U.S. Census Bureau ACS (Table B25077)",
    namePt: "U.S. Census Bureau ACS (Tabela B25077)",
    shortNameEn: "Census B25077",
    shortNamePt: "Censo B25077",
    url: "https://censusreporter.org/tables/B25077/",
    govUrl: "https://data.census.gov/table/B25077",
    linkLabelEn: "Open interactive table (Census Reporter) ↗",
    linkLabelPt: "Abrir tabela interativa (Census Reporter) ↗",
    whyEn:
      "Median property valuation provides the baseline anchor for discount margins, wholesaling spreads, and maximum allowable acquisition offers in each county.",
    whyPt:
      "A mediana de valor venal serve como âncora financeira para cálculo de margens de desconto, spreads de repasse e teto máximo de oferta de compra à vista no condado.",
  },
  free_and_clear_pct: {
    nameEn: "U.S. Census Bureau ACS (Table B25081)",
    namePt: "U.S. Census Bureau ACS (Tabela B25081)",
    shortNameEn: "Census B25081",
    shortNamePt: "Censo B25081",
    url: "https://censusreporter.org/tables/B25081/",
    govUrl: "https://data.census.gov/table/B25081",
    linkLabelEn: "Open interactive table (Census Reporter) ↗",
    linkLabelPt: "Abrir tabela interativa (Census Reporter) ↗",
    whyEn:
      "Homeowners without a bank mortgage have 100% equity with zero lender payoff requirements. This gives them full flexibility to accept an as-is cash offer with quick 7–14 day closing.",
    whyPt:
      "Proprietários sem hipoteca bancária têm 100% do patrimônio líquido livre sem saldo devedor a quitar. Isso garante total flexibilidade para aceitar ofertas à vista com fechamento rápido em 7 a 14 dias.",
  },
  owner_long_tenure_pct: {
    nameEn: "U.S. Census Bureau ACS (Table B25038)",
    namePt: "U.S. Census Bureau ACS (Tabela B25038)",
    shortNameEn: "Census B25038",
    shortNamePt: "Censo B25038",
    url: "https://censusreporter.org/tables/B25038/",
    govUrl: "https://data.census.gov/table/B25038",
    linkLabelEn: "Open interactive table (Census Reporter) ↗",
    linkLabelPt: "Abrir tabela interativa (Census Reporter) ↗",
    whyEn:
      "Homeowners of 20+ years frequently carry deferred maintenance, aging roofs/systems, or life transitions (probate/retirement). An as-is sale eliminates $30k–$80k in retail remodeling costs.",
    whyPt:
      "Famílias no imóvel há mais de 20 anos frequentemente acumulam manutenções pendentes ou transições de vida (aposentadoria/herança). Vender no estado atual elimina $30k–$80k em reformas.",
  },
  median_year_built: {
    nameEn: "U.S. Census Bureau ACS (Table B25035)",
    namePt: "U.S. Census Bureau ACS (Tabela B25035)",
    shortNameEn: "Census B25035",
    shortNamePt: "Censo B25035",
    url: "https://censusreporter.org/tables/B25035/",
    govUrl: "https://data.census.gov/table/B25035",
    linkLabelEn: "Open interactive table (Census Reporter) ↗",
    linkLabelPt: "Abrir tabela interativa (Census Reporter) ↗",
    whyEn:
      "Older housing stock correlates with aging electrical, plumbing, and structural components that fail buyer mortgage inspections, strongly favoring cash buyers who waive repairs.",
    whyPt:
      "Imóveis mais antigos acumulam desgaste estrutural e reprovam em vistorias de bancos, favorecendo compradores que compram à vista sem exigir reformas prévias.",
  },
  vacancy_pct: {
    nameEn: "U.S. Census Bureau ACS (Table B25002)",
    namePt: "U.S. Census Bureau ACS (Tabela B25002)",
    shortNameEn: "Census B25002",
    shortNamePt: "Censo B25002",
    url: "https://censusreporter.org/tables/B25002/",
    govUrl: "https://data.census.gov/table/B25002",
    linkLabelEn: "Open interactive table (Census Reporter) ↗",
    linkLabelPt: "Abrir tabela interativa (Census Reporter) ↗",
    whyEn:
      "Unoccupied properties generate zero income while accumulating property taxes, insurance, and deterioration, creating urgency for motivated sellers to liquidate quickly.",
    whyPt:
      "Casas desocupadas não geram renda e continuam acumulando IPTU local, seguro e desgaste físico, criando forte motivação para venda rápida à vista.",
  },
  hail_reports_1in: {
    nameEn: "NOAA Storm Events Database (2020–2024)",
    namePt: "Base de Tempestades da NOAA (2020–2024)",
    shortNameEn: "NOAA Storm Events",
    shortNamePt: "NOAA Tempestades",
    url: "https://www.ncei.noaa.gov/access/storm-events-database/",
    govUrl: null,
    linkLabelEn: "Open official NOAA Storm Events database ↗",
    linkLabelPt: "Abrir base oficial NOAA de Tempestades ↗",
    whyEn:
      "Severe hail (>= 1.0 inch) damages roofs and siding. Homeowners facing insurance deductibles or out-of-pocket restoration costs often prefer an immediate as-is cash sale.",
    whyPt:
      "Granizo severo perfura telhados e danifica fachadas. Proprietários sem verba para franquia de seguro ou reformas preferem vender a casa à vista no estado em que se encontra.",
  },
  wind_reports_50kt: {
    nameEn: "NOAA Storm Events Database (2020–2024)",
    namePt: "Base de Tempestades da NOAA (2020–2024)",
    shortNameEn: "NOAA High Wind",
    shortNamePt: "NOAA Vendavais",
    url: "https://www.ncei.noaa.gov/access/storm-events-database/",
    govUrl: null,
    linkLabelEn: "Open official NOAA Storm Events database ↗",
    linkLabelPt: "Abrir base oficial NOAA de Tempestades ↗",
    whyEn:
      "Gale-force winds cause structural damage and fallen trees, leading owners to seek fast cash liquidation over lengthy insurance restoration delays.",
    whyPt:
      "Vendavais severos causam destelhamento e danos estruturais, levando proprietários a buscar liquidação rápida em vez de aguardar restaurações demoradas.",
  },
  tropical_storm_events: {
    nameEn: "NOAA & NWS Zone Weather Database",
    namePt: "Base Meteorológica NOAA & NWS",
    shortNameEn: "NOAA Coastal",
    shortNamePt: "NOAA Costeira",
    url: "https://www.ncei.noaa.gov/access/storm-events-database/",
    govUrl: null,
    linkLabelEn: "Open official NOAA Storm Events database ↗",
    linkLabelPt: "Abrir base oficial NOAA de Tempestades ↗",
    whyEn:
      "Tropical storm and hurricane exposure creates flood and wind risks, prompting owners in coastal counties to capitalize on equity via quick off-market sales.",
    whyPt:
      "Exposição a furacões e tempestades tropicais cria riscos recorrentes de inundação e vento, acelerando a decisão de venda de proprietários em áreas costeiras.",
  },
};

function renderFactsSection(campaign) {
  const section = el("section", "pkg-section");
  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("factsTitle")));
  const facts = Array.isArray(campaign.facts) ? campaign.facts : [];
  head.appendChild(el("span", "badge badge-neutral", `${facts.length}`));
  section.appendChild(head);
  section.appendChild(el("p", "pkg-section-subtitle", t("factsSubtitle")));

  const correctionsByField = new Map();
  if (Array.isArray(campaign.corrections)) {
    for (const corr of campaign.corrections) {
      correctionsByField.set(corr.field, corr);
    }
  }

  const grid = el("div", "item-grid item-grid-2");
  for (const fact of facts) {
    const isCorrected = fact.status === "corrected";
    const card = el("article", isCorrected ? "sub-card sub-card-corrected" : "sub-card");

    const top = el("div", "sub-card-top");
    const statusLabel = tNested("factStatuses", fact.status, fact.status);
    top.appendChild(el("span", statusBadgeClass(fact.status), statusLabel));
    top.appendChild(el("span", "badge badge-blue", fact.source || ""));
    card.appendChild(top);

    card.appendChild(el("p", "sub-card-text", fact.claim || ""));

    const detailLine = el(
      "p",
      "sub-card-meta",
      `${t("fieldLabel")} ${fact.field} · ${t("valueLabel")} ${fact.value}`
    );
    card.appendChild(detailLine);

    const insight = METRIC_INSIGHTS[fact.field];
    if (insight) {
      const isPt = state.lang === "pt";
      const whyBox = el("div", "fact-why-box");
      whyBox.appendChild(
        el(
          "strong",
          "fact-why-label",
          isPt ? "💡 Por que este número importa na negociação:" : "💡 Why this metric matters for campaigns:"
        )
      );
      whyBox.appendChild(el("p", "fact-why-text", isPt ? insight.whyPt : insight.whyEn));

      const linkRow = el("div", "fact-why-link-row");
      const a = document.createElement("a");
      a.className = "fact-dataset-link";
      a.href = insight.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = isPt ? insight.linkLabelPt : insight.linkLabelEn;
      linkRow.appendChild(a);

      if (insight.govUrl) {
        const govA = document.createElement("a");
        govA.className = "fact-dataset-link fact-dataset-link-secondary";
        govA.href = insight.govUrl;
        govA.target = "_blank";
        govA.rel = "noopener noreferrer";
        govA.textContent = isPt
          ? "Portal oficial data.census.gov ↗"
          : "Official data.census.gov portal ↗";
        linkRow.appendChild(govA);
      }
      whyBox.appendChild(linkRow);

      card.appendChild(whyBox);
    }

    if (isCorrected && correctionsByField.has(fact.field)) {
      const corr = correctionsByField.get(fact.field);
      const deltaText = t("auditDelta", {
        llm: corr.llm_value,
        source: corr.source_value,
      });
      card.appendChild(el("span", "badge badge-corrected", deltaText));
    }

    grid.appendChild(card);
  }
  section.appendChild(grid);
  return section;
}

function renderQuestionsSection(campaign) {
  const section = el("section", "pkg-section");
  const questions = campaign.assets?.questions || [];

  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("questionsTitle")));
  head.appendChild(el("span", "badge badge-neutral", `${questions.length}`));
  section.appendChild(head);

  const grid = el("div", "item-grid");
  for (const q of questions) {
    const card = el("article", "sub-card");
    const top = el("div", "sub-card-top");

    const leftBadges = el("div", "badge-row");
    leftBadges.appendChild(el("span", "badge badge-mono badge-neutral", `Q${q.question_index}`));
    if (q.topic) {
      leftBadges.appendChild(el("span", "badge badge-indigo", formatTopicLabel(q.topic)));
    }
    top.appendChild(leftBadges);
    top.appendChild(
      el("span", statusBadgeClass(q.status), tNested("assetStatuses", q.status, q.status))
    );
    card.appendChild(top);

    card.appendChild(el("p", "sub-card-text", q.question || ""));
    if (q.why) {
      card.appendChild(el("p", "sub-card-meta", `${t("whyLabel")} ${q.why}`));
    }
    grid.appendChild(card);
  }

  section.appendChild(grid);
  return section;
}

function renderInlineReviewCallout(reviewItem) {
  const box = el("div", "human-review-callout");
  const top = el("div", "human-review-callout-top");
  top.appendChild(el("span", "badge badge-yellow", t("inlineReviewBadge")));
  top.appendChild(el("span", "badge badge-mono badge-neutral", `${t("ruleLabel")} ${reviewItem.rule_id}`));
  box.appendChild(top);
  box.appendChild(el("p", "human-review-callout-text", reviewItem.reason));
  return box;
}

function formatReviewItemName(name) {
  if (name.startsWith("headline_")) {
    return `${t("headlineWord")} ${name.split("_")[1]}`;
  }
  if (name.startsWith("description_")) {
    return `${t("descriptionWord")} ${name.split("_")[1]}`;
  }
  if (name === "lp_subheadline") return t("lpSubheadlineWord");
  if (name === "lp_headline") return t("lpHeadlineWord");
  if (name.startsWith("sms_")) {
    return `SMS ${name.split("_")[1]}`;
  }
  if (name.startsWith("email_")) {
    return `Email ${name.split("_")[1]}`;
  }
  return name;
}

function renderReviewAlertBanner(campaign) {
  const items = Array.isArray(campaign.needs_human_review) ? campaign.needs_human_review : [];
  if (items.length === 0) return null;

  const banner = el("div", "review-alert-banner");
  banner.appendChild(el("div", "review-alert-icon", "⚠️"));

  const content = el("div", "review-alert-content");
  content.appendChild(el("h4", "review-alert-title", t("reviewAlertTitle", { n: items.length })));
  content.appendChild(el("p", "review-alert-desc", t("reviewAlertDesc")));

  const tags = el("div", "review-alert-tags");
  for (const item of items) {
    const formattedItem = formatReviewItemName(item.item);
    tags.appendChild(el("span", "badge badge-yellow", `${formattedItem}: ${item.rule_id}`));
  }
  content.appendChild(tags);
  banner.appendChild(content);

  return banner;
}

function renderAdsSection(campaign) {
  const section = el("section", "pkg-section");
  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("adsTitle")));

  const adReviewItems = (campaign.needs_human_review || []).filter(
    (r) => r.item.startsWith("headline_") || r.item.startsWith("description_")
  );
  if (adReviewItems.length > 0) {
    head.appendChild(el("span", "badge badge-yellow", t("sectionFlaggedBadge", { n: adReviewItems.length })));
  }
  section.appendChild(head);

  const adCopy = campaign.assets?.ad_copy || { headlines: [], descriptions: [] };
  const split = el("div", "ads-split");

  // Headlines column
  const hCol = el("div");
  hCol.appendChild(el("h5", "ads-col-title", t("headlinesHeading")));
  (adCopy.headlines || []).forEach((item, idx) => {
    const itemName = `headline_${idx + 1}`;
    const itemReviews = (campaign.needs_human_review || []).filter((r) => r.item === itemName);
    const isFlagged = itemReviews.length > 0;

    const wrapper = el("div", isFlagged ? "copy-row-wrap copy-row-wrap-flagged" : "copy-row-wrap");
    const row = el("div", isFlagged ? "copy-row copy-row-flagged" : "copy-row");
    row.appendChild(el("span", "copy-row-text", item.text || ""));
    const pills = el("div", "copy-row-pills");
    const len = (item.text || "").length;
    const ok = len <= LIMITS.headline;
    pills.appendChild(
      el(
        "span",
        `badge badge-mono ${ok ? "badge-green" : "badge-red"}`,
        `${len}/${LIMITS.headline} ${t("charsUnit")}`
      )
    );
    if (isFlagged) {
      pills.appendChild(el("span", "badge badge-yellow", t("needsReviewPill")));
    } else {
      pills.appendChild(
        el("span", statusBadgeClass(item.status), tNested("assetStatuses", item.status, item.status))
      );
    }
    row.appendChild(pills);
    wrapper.appendChild(row);

    for (const rev of itemReviews) {
      wrapper.appendChild(renderInlineReviewCallout(rev));
    }
    hCol.appendChild(wrapper);
  });
  split.appendChild(hCol);

  // Descriptions column
  const dCol = el("div");
  dCol.appendChild(el("h5", "ads-col-title", t("descriptionsHeading")));
  (adCopy.descriptions || []).forEach((item, idx) => {
    const itemName = `description_${idx + 1}`;
    const itemReviews = (campaign.needs_human_review || []).filter((r) => r.item === itemName);
    const isFlagged = itemReviews.length > 0;

    const wrapper = el("div", isFlagged ? "copy-row-wrap copy-row-wrap-flagged" : "copy-row-wrap");
    const row = el("div", isFlagged ? "copy-row copy-row-flagged" : "copy-row");
    row.appendChild(el("span", "copy-row-text", item.text || ""));
    const pills = el("div", "copy-row-pills");
    const len = (item.text || "").length;
    const ok = len <= LIMITS.description;
    pills.appendChild(
      el(
        "span",
        `badge badge-mono ${ok ? "badge-green" : "badge-red"}`,
        `${len}/${LIMITS.description} ${t("charsUnit")}`
      )
    );
    if (isFlagged) {
      pills.appendChild(el("span", "badge badge-yellow", t("needsReviewPill")));
    } else {
      pills.appendChild(
        el("span", statusBadgeClass(item.status), tNested("assetStatuses", item.status, item.status))
      );
    }
    row.appendChild(pills);
    wrapper.appendChild(row);

    for (const rev of itemReviews) {
      wrapper.appendChild(renderInlineReviewCallout(rev));
    }
    dCol.appendChild(wrapper);
  });
  split.appendChild(dCol);

  section.appendChild(split);
  return section;
}

function renderLandingPageSection(campaign) {
  const section = el("section", "pkg-section");
  const lp = campaign.assets?.landing_page;
  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("landingTitle")));

  const lpReviewItems = (campaign.needs_human_review || []).filter(
    (r) => r.item.startsWith("lp_") || r.item === "landing_page"
  );
  if (lpReviewItems.length > 0) {
    head.appendChild(el("span", "badge badge-yellow", t("sectionFlaggedBadge", { n: lpReviewItems.length })));
  } else if (lp?.status) {
    head.appendChild(
      el("span", statusBadgeClass(lp.status), tNested("assetStatuses", lp.status, lp.status))
    );
  }
  section.appendChild(head);

  if (!lp) return section;

  const preview = el("div", "lp-preview");

  // Headline
  const hReviews = (campaign.needs_human_review || []).filter((r) => r.item === "lp_headline");
  const hWrap = el("div", "lp-field-block");
  hWrap.appendChild(el("h5", "lp-headline", lp.headline || ""));
  for (const rev of hReviews) {
    hWrap.appendChild(renderInlineReviewCallout(rev));
  }
  preview.appendChild(hWrap);

  // Subheadline
  const subReviews = (campaign.needs_human_review || []).filter((r) => r.item === "lp_subheadline");
  const subWrap = el("div", "lp-field-block");
  subWrap.appendChild(el("p", "lp-subheadline", lp.subheadline || ""));
  for (const rev of subReviews) {
    subWrap.appendChild(renderInlineReviewCallout(rev));
  }
  preview.appendChild(subWrap);

  if (lp.cta_text) {
    const ctaReviews = (campaign.needs_human_review || []).filter((r) => r.item === "lp_cta_text");
    const ctaWrap = el("div", "lp-field-block");
    ctaWrap.appendChild(el("div", "lp-cta-preview", `${t("ctaPreviewLabel")} ${lp.cta_text}`));
    for (const rev of ctaReviews) {
      ctaWrap.appendChild(renderInlineReviewCallout(rev));
    }
    preview.appendChild(ctaWrap);
  }

  if (Array.isArray(lp.bullet_points) && lp.bullet_points.length > 0) {
    const ul = el("ul", "lp-bullets");
    lp.bullet_points.forEach((bp, idx) => {
      const bReviews = (campaign.needs_human_review || []).filter((r) => r.item === `lp_bullet_${idx + 1}`);
      const li = el("li", "lp-bullet-item");
      li.appendChild(el("span", "lp-bullet-icon", "✓"));
      li.appendChild(el("span", "lp-bullet-text", bp));
      ul.appendChild(li);
      for (const rev of bReviews) {
        ul.appendChild(renderInlineReviewCallout(rev));
      }
    });
    preview.appendChild(ul);
  }

  if (lp.consent_disclosure) {
    const consentReviews = (campaign.needs_human_review || []).filter(
      (r) => r.item === "lp_consent_disclosure"
    );
    const tcpa = el("div", "tcpa-box");
    const badgeRow = el("div", "badge-row");
    badgeRow.appendChild(el("span", "badge badge-blue", t("tcpaBadge")));
    tcpa.appendChild(badgeRow);
    tcpa.appendChild(el("p", "tcpa-text", lp.consent_disclosure));
    for (const rev of consentReviews) {
      tcpa.appendChild(renderInlineReviewCallout(rev));
    }
    preview.appendChild(tcpa);
  }

  section.appendChild(preview);
  return section;
}

function detectOptOutKeyword(text) {
  const upper = String(text || "").toUpperCase();
  for (const kw of OPT_OUT_KEYWORDS) {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`\\b${escaped}\\b`, "i").test(upper)) {
      return kw;
    }
  }
  return null;
}

function renderFollowUpSection(campaign) {
  const section = el("section", "pkg-section");
  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("followupTitle")));

  const followupReviews = (campaign.needs_human_review || []).filter(
    (r) => r.item.startsWith("sms_") || r.item.startsWith("email_")
  );
  if (followupReviews.length > 0) {
    head.appendChild(el("span", "badge badge-yellow", t("sectionFlaggedBadge", { n: followupReviews.length })));
  }
  section.appendChild(head);

  const expectedBrand = BRAND_BY_VERTICAL[campaign.vertical] || "Example Home Buyers";
  const smsList = campaign.assets?.sms_messages || [];
  const emailList = campaign.assets?.email_followups || [];

  // SMS subsection
  const smsHeading = el("h5", "ads-col-title", t("smsHeading"));
  section.appendChild(smsHeading);

  const smsGrid = el("div", "item-grid item-grid-2");
  for (const sms of smsList) {
    const itemName = `sms_${sms.message_index}`;
    const itemReviews = (campaign.needs_human_review || []).filter((r) => r.item === itemName);
    const isFlagged = itemReviews.length > 0;

    const card = el("article", isFlagged ? "sub-card sub-card-corrected" : "sub-card");
    const top = el("div", "sub-card-top");
    top.appendChild(el("span", "badge badge-mono badge-neutral", t("smsLabel", { n: sms.message_index })));

    const pills = el("div", "badge-row");
    if (isFlagged) {
      pills.appendChild(el("span", "badge badge-yellow", t("needsReviewPill")));
    }
    const charCount = Number.isFinite(sms.char_count) ? sms.char_count : (sms.text || "").length;
    const lenOk = charCount <= LIMITS.sms;
    pills.appendChild(
      el(
        "span",
        `badge badge-mono ${lenOk ? "badge-green" : "badge-red"}`,
        `${charCount}/${LIMITS.sms} ${t("charsUnit")}`
      )
    );

    const hasBrand = String(sms.text || "").toLowerCase().includes(expectedBrand.toLowerCase());
    pills.appendChild(
      el(
        "span",
        hasBrand ? "badge badge-indigo" : "badge badge-red",
        hasBrand ? t("brandBadge", { brand: expectedBrand }) : t("brandMissingBadge")
      )
    );

    const optOutKw = detectOptOutKeyword(sms.text);
    pills.appendChild(
      el(
        "span",
        optOutKw ? "badge badge-green" : "badge badge-red",
        optOutKw ? t("optOutBadge", { keyword: optOutKw }) : t("optOutMissingBadge")
      )
    );

    top.appendChild(pills);
    card.appendChild(top);
    card.appendChild(el("p", "sub-card-text", sms.text || ""));

    for (const rev of itemReviews) {
      card.appendChild(renderInlineReviewCallout(rev));
    }
    smsGrid.appendChild(card);
  }
  section.appendChild(smsGrid);

  // Emails subsection
  const emailHeading = el("h5", "ads-col-title", t("emailHeading"));
  emailHeading.style.marginTop = "16px";
  section.appendChild(emailHeading);

  const emailGrid = el("div", "item-grid item-grid-2");
  for (const em of emailList) {
    const itemName = `email_${em.email_index}`;
    const itemReviews = (campaign.needs_human_review || []).filter((r) => r.item === itemName);
    const isFlagged = itemReviews.length > 0;

    const card = el("article", isFlagged ? "sub-card sub-card-corrected" : "sub-card");
    const top = el("div", "sub-card-top");
    top.appendChild(el("span", "badge badge-mono badge-neutral", t("emailLabel", { n: em.email_index })));
    if (isFlagged) {
      top.appendChild(el("span", "badge badge-yellow", t("needsReviewPill")));
    } else {
      top.appendChild(
        el("span", statusBadgeClass(em.status), tNested("assetStatuses", em.status, em.status))
      );
    }
    card.appendChild(top);

    const subj = el("p", "sub-card-text");
    subj.style.fontWeight = "700";
    subj.textContent = `${t("subjectLabel")} ${em.subject || ""}`;
    card.appendChild(subj);

    card.appendChild(el("p", "email-body", em.body || ""));

    for (const rev of itemReviews) {
      card.appendChild(renderInlineReviewCallout(rev));
    }
    emailGrid.appendChild(card);
  }
  section.appendChild(emailGrid);

  return section;
}

function renderHumanReviewSection(campaign) {
  const section = el("section", "pkg-section");
  const items = Array.isArray(campaign.needs_human_review) ? campaign.needs_human_review : [];

  const head = el("div", "pkg-section-head");
  head.appendChild(el("h4", "pkg-section-title", t("reviewTitle")));
  if (items.length > 0) {
    head.appendChild(el("span", "badge badge-yellow", t("reviewFlaggedCount", { n: items.length })));
  } else {
    head.appendChild(el("span", "badge badge-green", t("reviewCleanBadge")));
  }
  section.appendChild(head);

  if (items.length > 0) {
    const grid = el("div", "item-grid");
    for (const item of items) {
      const card = el("article", "sub-card sub-card-corrected");
      const top = el("div", "sub-card-top");
      top.appendChild(el("span", "badge badge-yellow", item.item || ""));
      top.appendChild(el("span", "badge badge-mono badge-neutral", `${t("ruleLabel")} ${item.rule_id}`));
      card.appendChild(top);
      card.appendChild(el("p", "sub-card-text", item.reason || ""));
      grid.appendChild(card);
    }
    section.appendChild(grid);
  } else {
    const emptyCard = el("div", "sub-card");
    emptyCard.appendChild(el("p", "sub-card-text", t("reviewEmptyMsg")));
    section.appendChild(emptyCard);
  }

  const standing = el("p", "sub-card-meta", t("reviewStandingNote"));
  standing.style.marginTop = "10px";
  section.appendChild(standing);

  return section;
}

function renderCampaignPackage(container, campaign, inputAssumptions, sectionFilter = "all") {
  clearNode(container);
  if (!campaign) return;

  if (sectionFilter === "all") {
    const banner = renderReviewAlertBanner(campaign);
    if (banner) container.appendChild(banner);
  }

  const builders = {
    economics: () => renderUnitEconomicsSection(campaign, inputAssumptions),
    facts: () => renderFactsSection(campaign),
    questions: () => renderQuestionsSection(campaign),
    ads: () => renderAdsSection(campaign),
    landing: () => renderLandingPageSection(campaign),
    followup: () => renderFollowUpSection(campaign),
    review: () => renderHumanReviewSection(campaign),
  };

  const order =
    sectionFilter === "all"
      ? ["economics", "facts", "questions", "ads", "landing", "followup", "review"]
      : [sectionFilter];

  for (const key of order) {
    if (builders[key]) container.appendChild(builders[key]());
  }
}

function renderPackageHeader(titleEl, badgesEl, campaign) {
  if (!campaign) return;
  titleEl.textContent = campaign.county_name;
  clearNode(badgesEl);
  badgesEl.appendChild(el("span", "badge badge-mono badge-neutral", `FIPS ${campaign.county_fips}`));
  badgesEl.appendChild(
    el("span", "badge badge-indigo", tNested("verticalLabels", campaign.vertical, campaign.vertical))
  );
  const verdict = campaign.unit_economics?.verdict || "red";
  badgesEl.appendChild(
    el("span", verdictPillClass(verdict), tNested("verdicts", verdict, verdict.toUpperCase()))
  );
}

function renderActiveExample() {
  const campaigns = getCampaignsList();
  const active = campaigns.find((c) => c.county_fips === state.activeCountyFips) || campaigns[0];
  if (!active) return;

  renderPackageHeader($("activeCountyTitle"), $("activeCountyBadges"), active);
  const inputAssumptions = state.examples?.canonical_inputs?.[active.county_fips] || null;
  renderCampaignPackage($("exampleViewer"), active, inputAssumptions, state.activeSection);
}

/* ------------------------------------------------------------------------------ Markdown Export */

function campaignToMarkdown(campaign, inputAssumptions) {
  if (!campaign) return "";
  const econ = campaign.unit_economics || {};
  const lines = [];
  lines.push(`# ${campaign.county_name} (FIPS ${campaign.county_fips})`);
  lines.push(`- **Vertical:** ${campaign.vertical}`);
  lines.push(`- **Traffic Light Verdict:** ${String(econ.verdict || "").toUpperCase()}`);
  lines.push("");

  lines.push("## Unit Economics");
  lines.push(`- **Lead Bid:** ${fmtUsd(econ.bid_per_lead_usd)}`);
  lines.push(`- **Best-Case CPL:** ${fmtUsd(econ.cpl_best_usd)}`);
  lines.push(`- **Worst-Case CPL:** ${fmtUsd(econ.cpl_worst_usd)}`);
  lines.push(`- **Max Viable CPC:** ${fmtUsd(econ.max_cpc_usd)}`);
  if (inputAssumptions?.cpc_usd && inputAssumptions?.landing_cvr) {
    lines.push(
      `- **Operator Assumptions:** CPC ${fmtUsd(inputAssumptions.cpc_usd.min)}–${fmtUsd(
        inputAssumptions.cpc_usd.max
      )}, CVR ${fmtPct(inputAssumptions.landing_cvr.min)}–${fmtPct(inputAssumptions.landing_cvr.max)}`
    );
  }
  lines.push(`- **Explanation:** ${econ.explanation || ""}`);
  lines.push("");

  lines.push("## Verified Facts");
  for (const f of campaign.facts || []) {
    lines.push(`- [${f.status}] ${f.claim} (field: \`${f.field}\`, value: \`${f.value}\`, source: ${f.source})`);
  }
  if (Array.isArray(campaign.corrections) && campaign.corrections.length > 0) {
    lines.push("");
    lines.push("### Automated Corrections");
    for (const c of campaign.corrections) {
      lines.push(`- \`${c.field}\`: LLM \`${c.llm_value}\` -> Official \`${c.source_value}\` (${c.reason})`);
    }
  }
  lines.push("");

  lines.push("## Qualification Questions");
  for (const q of campaign.assets?.questions || []) {
    lines.push(`${q.question_index}. **[${formatTopicLabel(q.topic)}]** ${q.question}`);
    if (q.why) lines.push(`   - Why: ${q.why}`);
  }
  lines.push("");

  lines.push("## Google Ads Responsive Search Ad Copy");
  lines.push("### Headlines");
  for (const h of campaign.assets?.ad_copy?.headlines || []) {
    lines.push(`- ${h.text} (${h.text.length}/30 chars)`);
  }
  lines.push("### Descriptions");
  for (const d of campaign.assets?.ad_copy?.descriptions || []) {
    lines.push(`- ${d.text} (${d.text.length}/90 chars)`);
  }
  lines.push("");

  const lp = campaign.assets?.landing_page;
  if (lp) {
    lines.push("## Landing Page Top");
    lines.push(`- **Headline:** ${lp.headline}`);
    lines.push(`- **Subheadline:** ${lp.subheadline}`);
    lines.push(`- **CTA:** ${lp.cta_text}`);
    for (const bp of lp.bullet_points || []) {
      lines.push(`  - ${bp}`);
    }
    lines.push(`- **TCPA Consent Disclosure:** ${lp.consent_disclosure}`);
    lines.push("");
  }

  lines.push("## Follow-Up Sequences");
  lines.push("### SMS Messages");
  for (const s of campaign.assets?.sms_messages || []) {
    const count = Number.isFinite(s.char_count) ? s.char_count : (s.text || "").length;
    lines.push(`- SMS #${s.message_index} (${count}/160 chars): ${s.text}`);
  }
  lines.push("### Follow-Up Emails");
  for (const em of campaign.assets?.email_followups || []) {
    lines.push(`- **Email #${em.email_index} — ${em.subject}**`);
    lines.push(em.body || "");
    lines.push("");
  }

  lines.push("## Human Review Checklist");
  const reviewItems = campaign.needs_human_review || [];
  if (reviewItems.length === 0) {
    lines.push("- No automated claim flags triggered. Confirm TCPA quiet hours (8 a.m.–9 p.m. local time) and final buyer offer terms before launch.");
  } else {
    for (const r of reviewItems) {
      lines.push(`- **${r.item}** (\`${r.rule_id}\`): ${r.reason}`);
    }
  }

  return lines.join("\n");
}

async function copyCampaignMarkdown(button, campaign, inputAssumptions) {
  const md = campaignToMarkdown(campaign, inputAssumptions);
  if (!md) return;
  let ok = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(md);
      ok = true;
    }
  } catch {
    ok = false;
  }

  if (!ok) {
    try {
      const ta = el("textarea");
      ta.value = md;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand("copy");
      document.body.removeChild(ta);
    } catch {
      ok = false;
    }
  }

  button.textContent = ok ? t("copiedMarkdown") : t("copyFailed");
  window.setTimeout(() => {
    button.textContent = t("copyMarkdown");
  }, COPIED_FEEDBACK_MS);
}

/* ------------------------------------------------------------------------------ Tabs */

function selectMainTab(tabId, focusTab = false) {
  state.activeTab = tabId;
  const isLive = tabId === "tabLive";

  for (const id of MAIN_TAB_IDS) {
    const btn = $(id);
    if (!btn) continue;
    const selected = id === tabId;
    btn.classList.toggle("is-active", selected);
    btn.setAttribute("aria-selected", String(selected));
    btn.setAttribute("tabindex", selected ? "0" : "-1");
    if (selected && focusTab) btn.focus();
  }

  const clickedBtn = $(tabId);
  const fips = clickedBtn?.getAttribute("data-county-fips");
  if (fips) {
    state.activeCountyFips = fips;
    $("panelExamples").setAttribute("aria-labelledby", tabId);
  }

  $("panelExamples").hidden = isLive;
  $("panelLive").hidden = !isLive;

  if (!isLive) renderActiveExample();
}

function onMainTabKeyDown(event) {
  const idx = MAIN_TAB_IDS.indexOf(event.currentTarget.id);
  if (idx === -1) return;
  let nextIdx = null;
  if (event.key === "ArrowRight") nextIdx = (idx + 1) % MAIN_TAB_IDS.length;
  else if (event.key === "ArrowLeft") nextIdx = (idx - 1 + MAIN_TAB_IDS.length) % MAIN_TAB_IDS.length;
  else if (event.key === "Home") nextIdx = 0;
  else if (event.key === "End") nextIdx = MAIN_TAB_IDS.length - 1;
  if (nextIdx !== null) {
    event.preventDefault();
    selectMainTab(MAIN_TAB_IDS[nextIdx], true);
  }
}

function selectSectionFilter(sectionKey) {
  state.activeSection = sectionKey;
  for (const btn of document.querySelectorAll("#exampleSectionNav .sub-tab")) {
    const active = btn.getAttribute("data-section") === sectionKey;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  }
  renderActiveExample();
}

/* ------------------------------------------------------------------------------ Live County Run (SSE) */

function normalizeApiUrl(raw) {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (trimmed === "") return "";
  if (trimmed.startsWith("https://") || trimmed.startsWith("http://localhost") || trimmed.startsWith("http://127.0.0.1")) {
    return trimmed;
  }
  return "";
}

function renderLiveApiNotice() {
  const notice = $("liveApiNotice");
  if (!notice) return;
  if (state.apiUrl === "") {
    notice.textContent = t("apiUnconfiguredNotice");
    notice.hidden = false;
  } else {
    notice.hidden = true;
  }
}

function resetProgressStages() {
  state.stageStates = {};
  for (const stage of PROGRESS_STAGES) {
    state.stageStates[stage] = "pending";
  }
  renderProgressList();
}

function renderProgressList() {
  const list = $("liveProgressList");
  clearNode(list);
  PROGRESS_STAGES.forEach((stage, index) => {
    const status = state.stageStates[stage] || "pending";
    const li = el("li", `step-card step-${status}`);
    const badgeText = status === "done" ? "✓" : status === "failed" ? "!" : String(index + 1);
    li.appendChild(el("span", "step-badge", badgeText));
    li.appendChild(el("span", "step-label", tNested("stages", stage, stage)));
    list.appendChild(li);
  });
}

function markStageDone(stageName) {
  const idx = PROGRESS_STAGES.indexOf(stageName);
  if (idx === -1) return;
  for (let i = 0; i <= idx; i += 1) {
    state.stageStates[PROGRESS_STAGES[i]] = "done";
  }
  if (idx + 1 < PROGRESS_STAGES.length && state.stageStates[PROGRESS_STAGES[idx + 1]] === "pending") {
    state.stageStates[PROGRESS_STAGES[idx + 1]] = "running";
  }
  renderProgressList();
}

function markCurrentRunningFailed() {
  const running = PROGRESS_STAGES.find((s) => state.stageStates[s] === "running");
  const target = running || PROGRESS_STAGES[0];
  state.stageStates[target] = "failed";
  renderProgressList();
}

function showLiveError(message) {
  $("liveErrorText").textContent = message;
  $("liveErrorBanner").hidden = false;
  $("liveStatusArea").hidden = false;
}

function hideLiveError() {
  $("liveErrorBanner").hidden = true;
  $("liveErrorText").textContent = "";
}

function splitSseFrames(buffer) {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  return { frames: parts, rest };
}

function parseSseFrame(frameText) {
  let event = "message";
  const dataLines = [];
  for (const line of frameText.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  return { event, data: dataLines.join("\n") };
}

function isCountyCampaignShape(obj) {
  return (
    obj &&
    typeof obj === "object" &&
    typeof obj.county_fips === "string" &&
    typeof obj.county_name === "string" &&
    obj.unit_economics &&
    obj.assets
  );
}

function renderLiveResult(campaign, inputPayload) {
  state.liveCampaign = campaign;
  state.liveInputs = inputPayload;
  renderPackageHeader($("liveCountyTitle"), $("liveCountyBadges"), campaign);
  renderCampaignPackage($("liveViewer"), campaign, inputPayload, "all");
  $("liveResultContainer").hidden = false;
  announce(t("liveReadyAnnounce", { county: campaign.county_name }));
}

function setLiveBusy(busy) {
  const btn = $("liveRunBtn");
  btn.disabled = busy;
  btn.textContent = t(busy ? "liveRunningBtn" : "liveRunBtn");
}

function readAndValidateLiveForm() {
  const fips = $("liveFips").value.trim();
  const vertical = $("liveVertical").value;
  const bid = Number.parseFloat($("liveBid").value);
  const cpcMin = Number.parseFloat($("liveCpcMin").value);
  const cpcMax = Number.parseFloat($("liveCpcMax").value);
  const cvrMinPct = Number.parseFloat($("liveCvrMin").value);
  const cvrMaxPct = Number.parseFloat($("liveCvrMax").value);
  const accessCode = $("liveAccessCode").value;

  if (!/^\d{5}$/.test(fips)) return null;
  if (!Number.isFinite(bid) || bid <= 0) return null;
  if (!Number.isFinite(cpcMin) || !Number.isFinite(cpcMax) || cpcMin < 0 || cpcMin > cpcMax) return null;
  if (
    !Number.isFinite(cvrMinPct) ||
    !Number.isFinite(cvrMaxPct) ||
    cvrMinPct <= 0 ||
    cvrMaxPct > 100 ||
    cvrMinPct > cvrMaxPct
  ) {
    return null;
  }

  return {
    accessCode,
    payload: {
      county_fips: fips,
      vertical: vertical === "roofing" ? "roofing" : "motivated_seller",
      bid_per_lead_usd: bid,
      cpc_usd: { min: cpcMin, max: cpcMax },
      landing_cvr: {
        min: Number((cvrMinPct / 100).toFixed(4)),
        max: Number((cvrMaxPct / 100).toFixed(4)),
      },
    },
  };
}

async function handleLiveErrorResponse(response) {
  if (response.status === 401) {
    return showLiveError(t("errUnauthorized"));
  }
  if (response.status === 429) {
    const retryAfter = Number.parseInt(response.headers.get("Retry-After") || "", 10);
    if (Number.isFinite(retryAfter) && retryAfter >= 0) {
      return showLiveError(t("errRateLimited", { seconds: retryAfter }));
    }
    return showLiveError(t("errRateLimitedNoWait"));
  }
  if (response.status === 422) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail || "");
    return showLiveError(t("errValidation", { detail: detail || "Invalid input" }));
  }
  if (response.status === 404 || response.status === 405) {
    return showLiveError(t("errApiOffline"));
  }
  return showLiveError(t("errServer", { status: response.status }));
}

async function readLiveSseStream(response, runId, inputPayload) {
  if (!response.body) {
    markCurrentRunningFailed();
    showLiveError(t("errBadStream"));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let completed = false;
  let failed = false;

  for (;;) {
    const { value, done } = await reader.read();
    if (runId !== state.liveRunId) {
      await reader.cancel().catch(() => undefined);
      return;
    }

    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");
    const { frames, rest } = splitSseFrames(done ? `${buffer}\n\n` : buffer);
    buffer = done ? "" : rest;

    for (const rawFrame of frames) {
      if (!rawFrame.trim()) continue;
      const frame = parseSseFrame(rawFrame);
      let data = null;
      try {
        data = JSON.parse(frame.data);
      } catch {
        failed = true;
        markCurrentRunningFailed();
        showLiveError(t("errBadStream"));
        break;
      }

      if (frame.event === "progress" && data?.stage) {
        markStageDone(data.stage);
      } else if (frame.event === "error") {
        failed = true;
        markCurrentRunningFailed();
        showLiveError(t("errStreamFailed"));
        break;
      } else if (frame.event === "done") {
        const campaign = isCountyCampaignShape(data)
          ? data
          : Array.isArray(data?.campaigns)
          ? data.campaigns[0]
          : null;
        if (!isCountyCampaignShape(campaign)) {
          failed = true;
          markCurrentRunningFailed();
          showLiveError(t("errBadStream"));
          break;
        }
        for (const stage of PROGRESS_STAGES) state.stageStates[stage] = "done";
        renderProgressList();
        renderLiveResult(campaign, inputPayload);
        completed = true;
        break;
      }
    }

    if (done || completed || failed) break;
  }

  if (!completed && !failed) {
    markCurrentRunningFailed();
    showLiveError(t("errBadStream"));
  }
  await reader.cancel().catch(() => undefined);
}

async function onLiveFormSubmit(event) {
  event.preventDefault();
  const parsed = readAndValidateLiveForm();
  if (!parsed) {
    $("liveStatusArea").hidden = false;
    resetProgressStages();
    showLiveError(t("errInvalidForm"));
    return;
  }

  const runId = ++state.liveRunId;
  hideLiveError();
  $("liveResultContainer").hidden = true;
  $("liveStatusArea").hidden = false;
  resetProgressStages();
  state.stageStates[PROGRESS_STAGES[0]] = "running";
  renderProgressList();
  setLiveBusy(true);

  const headers = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (parsed.accessCode) {
    headers["X-Access-Code"] = parsed.accessCode;
  }

  const endpoint = `${state.apiUrl}${STREAM_PATH}`;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), LIVE_TIMEOUT_MS);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(parsed.payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      markCurrentRunningFailed();
      await handleLiveErrorResponse(response);
    } else {
      await readLiveSseStream(response, runId, parsed.payload);
    }
  } catch (err) {
    markCurrentRunningFailed();
    showLiveError(err?.name === "AbortError" ? t("errTimeout") : t("errApiOffline"));
  } finally {
    window.clearTimeout(timeout);
    if (runId === state.liveRunId) {
      setLiveBusy(false);
    }
  }
}

/* ------------------------------------------------------------------------------ Init & Wiring */

function renderAllDynamic() {
  renderAuctionMathTable();
  renderCorrectionCallout();
  renderActiveExample();
  renderProgressList();
  if (state.liveCampaign) {
    renderLiveResult(state.liveCampaign, state.liveInputs);
  }
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function loadConfig() {
  try {
    const cfg = await loadJson("./config.json");
    state.apiUrl = normalizeApiUrl(cfg?.apiUrl ?? cfg?.apiBase ?? "");
  } catch {
    state.apiUrl = "";
  }
  renderLiveApiNotice();
}

async function loadExamples() {
  try {
    const data = await loadJson("./examples.json");
    state.examples = data;
    $("examplesError").hidden = true;
  } catch {
    state.examples = null;
    $("examplesError").textContent = t("errExamplesLoad");
    $("examplesError").hidden = false;
  }
}

function bindEvents() {
  $("langEn").addEventListener("click", () => setLang("en"));
  $("langPt").addEventListener("click", () => setLang("pt"));

  for (const id of MAIN_TAB_IDS) {
    const btn = $(id);
    if (!btn) continue;
    btn.addEventListener("click", () => selectMainTab(id, false));
    btn.addEventListener("keydown", onMainTabKeyDown);
  }

  for (const subBtn of document.querySelectorAll("#exampleSectionNav .sub-tab")) {
    subBtn.addEventListener("click", () => {
      selectSectionFilter(subBtn.getAttribute("data-section") || "all");
    });
  }

  $("copyMarkdownBtn").addEventListener("click", () => {
    const campaigns = getCampaignsList();
    const active = campaigns.find((c) => c.county_fips === state.activeCountyFips);
    const inputs = state.examples?.canonical_inputs?.[state.activeCountyFips] || null;
    copyCampaignMarkdown($("copyMarkdownBtn"), active, inputs);
  });

  $("copyLiveMarkdownBtn").addEventListener("click", () => {
    copyCampaignMarkdown($("copyLiveMarkdownBtn"), state.liveCampaign, state.liveInputs);
  });

  $("liveForm").addEventListener("submit", onLiveFormSubmit);

  $("fallbackExamplesBtn").addEventListener("click", () => {
    selectMainTab("tabCounty48113", false);
  });

  document.addEventListener("click", () => {
    document.querySelectorAll(".bullet-tooltip-anchor.is-open").forEach((el) => {
      el.classList.remove("is-open");
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".bullet-tooltip-anchor.is-open").forEach((el) => {
        el.classList.remove("is-open");
      });
    }
  });
}

async function init() {
  state.lang = initialLang();
  document.documentElement.lang = state.lang;
  $("langEn").classList.toggle("is-active", state.lang === "en");
  $("langEn").setAttribute("aria-pressed", String(state.lang === "en"));
  $("langPt").classList.toggle("is-active", state.lang === "pt");
  $("langPt").setAttribute("aria-pressed", String(state.lang === "pt"));

  bindEvents();
  applyStaticI18n();
  resetProgressStages();

  await Promise.all([loadConfig(), loadExamples()]);
  renderAllDynamic();
}

init();
