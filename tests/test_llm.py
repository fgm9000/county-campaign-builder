"""Unit tests for LLM DTOs, helpers, FakeModelClient, and AnthropicModelClient."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest
from anthropic.types import ContentBlock, Message, TextBlock, ToolUseBlock, Usage
from pydantic import ValidationError

from county_campaign_builder.county_data import CountyRecord, load_county_table
from county_campaign_builder.domain import QuestionTopic, VerticalConfig, load_verticals_config
from county_campaign_builder.llm import (
    COOK_FIPS,
    DALLAS_FIPS,
    DALLAS_TRAP_MEDIAN_HOME_VALUE,
    HAIKU_MODEL,
    PINELLAS_FIPS,
    SONNET_MODEL,
    AdsAndLandingPageOutput,
    AnthropicModelClient,
    ComparisonOutput,
    EmailItem,
    FakeModelClient,
    FollowupOutput,
    LlmError,
    LlmOutputError,
    QualificationQuestionItem,
    QualificationQuestionsOutput,
    RegeneratedAssetItem,
    RegenerateOutput,
    TriggerInterpretationOutput,
    TriggerItem,
    _build_compliant_sms,
    _extract_json_text,
    _fit_text,
    _format_trigger_claim,
    _short_county_name,
)
from county_campaign_builder.models import NumericFact
from county_campaign_builder.prompt import (
    AD_DESCRIPTION_MAX_CHARS,
    AD_HEADLINE_MAX_CHARS,
    CENSUS_SOURCE,
    NOAA_SOURCE,
    SMS_MAX_CHARS,
)


def _county_table() -> dict[str, CountyRecord]:
    project_root = Path(__file__).resolve().parents[1]
    return load_county_table(project_root / "data" / "counties.parquet")


def _make_arbitrary_county(
    *,
    fips: str = "99001",
    county_name: str = "Test County, Kansas",
    median_year_built: int | None = None,
    vacancy_pct: float | None = None,
    owner_long_tenure_pct: float | None = None,
    free_and_clear_pct: float | None = None,
    owner_occupied_pct: float | None = 62.5,
    median_home_value_usd: int | None = None,
) -> CountyRecord:
    return CountyRecord(
        fips=fips,
        county_name=county_name,
        hail_reports_1in=12,
        severe_wind_reports=8,
        tornado_events=1,
        tropical_events=0,
        years_covered="2020-2024",
        median_year_built=median_year_built,
        households=10000,
        owner_occupied=6250,
        owner_occupied_pct=owner_occupied_pct,
        housing_units=11000,
        vacant_units=1000,
        vacancy_pct=vacancy_pct,
        median_home_value_usd=median_home_value_usd,
        owner_long_tenure_pct=owner_long_tenure_pct,
        free_and_clear_pct=free_and_clear_pct,
    )


def _sample_facts() -> list[NumericFact]:
    return [
        NumericFact(
            claim="102 hail reports of 1 inch or larger in 2020-2024",
            field="hail_reports_1in",
            value=102,
            source=NOAA_SOURCE,
            status="verified",
        ),
        NumericFact(
            claim="42.69% of owner-occupied homes are owned free and clear",
            field="free_and_clear_pct",
            value=42.69,
            source=CENSUS_SOURCE,
            status="verified",
        ),
    ]


def _make_message(text: str | None, *, include_tool_use: bool = False) -> Message:
    blocks: list[ContentBlock] = []
    if include_tool_use:
        blocks.append(ToolUseBlock(id="tool_1", input={"a": 1}, name="helper", type="tool_use"))
    if text is not None:
        blocks.append(TextBlock(type="text", text=text))
    return Message(
        id="msg_test",
        content=blocks,
        model=HAIKU_MODEL,
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=20),
    )


def test_dtos_instantiate_and_validate() -> None:
    trigger = TriggerItem(
        claim="102 hail reports of 1 inch or larger in 2020-2024",
        field="hail_reports_1in",
        value=102,
        source=NOAA_SOURCE,
    )
    triggers_out = TriggerInterpretationOutput(triggers=[trigger])
    assert triggers_out.triggers[0].value == 102

    question_item = QualificationQuestionItem(
        question="How soon are you hoping to sell?",
        topic="timeline",
        why="Separates motivated sellers from browsers.",
    )
    questions_out = QualificationQuestionsOutput(questions=[question_item])
    assert questions_out.questions[0].topic == "timeline"

    ads_lp = AdsAndLandingPageOutput(
        headlines=["Sell Dallas Home As-Is", "Fair Cash Offer For Owners", "No Repairs Needed"],
        descriptions=[
            "Request a straightforward as-is cash offer for your Dallas home today.",
            "Skip cleanouts and showings. Review an offer on your preferred timeline.",
        ],
        lp_headline="Request an As-Is Cash Offer in Dallas County, Texas",
        lp_subheadline="Work directly with Example Home Buyers.",
        cta_text="Get My Offer",
        bullet_points=["As-is purchase", "Direct process", "No showings"],
        consent_disclosure=(
            "Agree to automated calls/texts. Consent is not a condition of purchase. Reply STOP."
        ),
    )
    assert len(ads_lp.headlines) == 3

    email = EmailItem(subject="Next steps", body="Thank you for reaching out.")
    followup = FollowupOutput(
        sms_messages=["Example Home Buyers: Thanks for reaching out. Reply STOP to opt out."],
        emails=[email],
    )
    assert followup.emails[0].subject == "Next steps"

    regen_item = RegeneratedAssetItem(item_id="headline_1", text="Sell Dallas Home As-Is")
    regen_out = RegenerateOutput(assets=[regen_item])
    assert regen_out.assets[0].item_id == "headline_1"

    comparison = ComparisonOutput(
        recommended_county_fips=DALLAS_FIPS,
        summary="Dallas County, TX is recommended.",
    )
    assert comparison.recommended_county_fips == DALLAS_FIPS


def test_dtos_are_frozen_and_reject_invalid_payloads() -> None:
    trigger = TriggerItem(claim="c", field="f", value=1, source=NOAA_SOURCE)
    with pytest.raises(ValidationError):
        trigger.__setattr__("claim", "mutated")

    with pytest.raises(ValidationError):
        TriggerInterpretationOutput.model_validate({"triggers": "not-a-list"})

    with pytest.raises(ValidationError):
        ComparisonOutput.model_validate({"recommended_county_fips": "48113"})


def test_llm_helpers_edge_cases() -> None:
    assert _short_county_name("Dallas County, Texas") == "Dallas"
    assert _short_county_name(" County") == "Local"
    assert _short_county_name("") == "Local"

    assert _fit_text("Short", "Fallback", 10) == "Short"
    assert _fit_text("Too long candidate", "Fits", 10) == "Fits"
    assert _fit_text("Too long candidate", "Fallback also too long", 8) == "Fallback"

    county = _make_arbitrary_county()
    assert "unknown custom metric is 7" in _format_trigger_claim("unknown_custom_metric", 7, county)
    assert "Median home value is $300,000" in _format_trigger_claim(
        "median_home_value_usd", 300000, county
    )

    long_brand = "A" * 150
    minimal_sms = _build_compliant_sms(long_brand, "Hello there")
    assert len(minimal_sms) <= SMS_MAX_CHARS

    trimmed_sms = _build_compliant_sms("Brand", "X" * 200)
    assert len(trimmed_sms) <= SMS_MAX_CHARS
    assert trimmed_sms.endswith("... Reply STOP to opt out.")

    assert _extract_json_text('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json_text('Some text\n```json\n{"a": 1}\n```\nMore text') == '{"a": 1}'
    assert _extract_json_text('Leading text {"a": 1} trailing text') == '{"a": 1}'
    assert _extract_json_text('{"a": 1}') == '{"a": 1}'
    assert _extract_json_text("plain text without braces") == "plain text without braces"


def test_fake_client_dallas_trap_and_grounded() -> None:
    table = _county_table()
    dallas = table[DALLAS_FIPS]
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]
    roofing = verticals.verticals["roofing"]

    client_trap = FakeModelClient(plant_trap=True)
    trap_out = client_trap.interpret_triggers(dallas, motivated_seller)
    assert len(trap_out.triggers) == 4
    median_items = [item for item in trap_out.triggers if item.field == "median_home_value_usd"]
    assert len(median_items) == 1
    assert median_items[0].value == DALLAS_TRAP_MEDIAN_HOME_VALUE
    assert dallas.median_home_value_usd == 303000

    # In roofing with trap, median_home_value_usd is trapped as well.
    trap_roofing = client_trap.interpret_triggers(dallas, roofing)
    assert sum(1 for item in trap_roofing.triggers if item.field == "median_home_value_usd") == 1

    client_clean = FakeModelClient(plant_trap=False)
    clean_out = client_clean.interpret_triggers(dallas, motivated_seller)
    clean_median = [item for item in clean_out.triggers if item.field == "median_home_value_usd"]
    assert len(clean_median) == 1
    assert clean_median[0].value == 303000


def test_fake_client_pinellas_cook_and_arbitrary_county() -> None:
    table = _county_table()
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]
    roofing = verticals.verticals["roofing"]
    client = FakeModelClient(plant_trap=False)

    pinellas_out = client.interpret_triggers(table[PINELLAS_FIPS], motivated_seller)
    assert len(pinellas_out.triggers) == 4
    assert all(item.source in {CENSUS_SOURCE, NOAA_SOURCE} for item in pinellas_out.triggers)

    cook_out = client.interpret_triggers(table[COOK_FIPS], roofing)
    assert len(cook_out.triggers) == 4

    # Arbitrary county with None values in some fields and fewer than 4 non-None trigger fields.
    sparse_county = _make_arbitrary_county(
        fips="99002",
        county_name="Sparse County, Nebraska",
        median_year_built=None,
        vacancy_pct=None,
        owner_long_tenure_pct=None,
        free_and_clear_pct=None,
        owner_occupied_pct=61.0,
        median_home_value_usd=None,
    )
    sparse_out = client.interpret_triggers(sparse_county, motivated_seller)
    fields = [item.field for item in sparse_out.triggers]
    assert "owner_long_tenure_pct" not in fields
    assert "vacancy_pct" not in fields
    assert "owner_occupied_pct" in fields
    assert "hail_reports_1in" in fields
    assert len(sparse_out.triggers) == 3


def test_fake_client_qualification_ads_followup_regen_and_compare() -> None:
    verticals = load_verticals_config()
    motivated_seller = verticals.verticals["motivated_seller"]
    roofing = verticals.verticals["roofing"]
    facts = _sample_facts()
    client = FakeModelClient()

    qual_ms = client.draft_qualification("Dallas County, Texas", motivated_seller, facts)
    assert len(qual_ms.questions) == 5

    custom_vertical = VerticalConfig(
        label="Custom",
        goal="Goal",
        trigger_fields=["hail_reports_1in"],
        required_question_topics=[
            QuestionTopic(topic="custom_topic", why="Custom rationale", keywords=["custom"])
        ],
        brand_name="Custom Brand",
    )
    qual_custom = client.draft_qualification("Dallas County, Texas", custom_vertical, [])
    assert len(qual_custom.questions) == 1
    assert "custom topic" in qual_custom.questions[0].question

    ads_ms = client.draft_ads_and_lp("Dallas County, Texas", motivated_seller, facts)
    assert len(ads_ms.headlines) == 5
    assert len(ads_ms.descriptions) == 3
    assert len(ads_ms.bullet_points) == 5
    assert all(len(h) <= AD_HEADLINE_MAX_CHARS for h in ads_ms.headlines)
    assert all(len(d) <= AD_DESCRIPTION_MAX_CHARS for d in ads_ms.descriptions)
    assert "automated" in ads_ms.consent_disclosure.lower()

    ads_roofing = client.draft_ads_and_lp("Dallas County, Texas", roofing, [])
    assert len(ads_roofing.headlines) == 5
    assert len(ads_roofing.descriptions) == 3
    assert len(ads_roofing.bullet_points) == 5
    assert all(len(h) <= AD_HEADLINE_MAX_CHARS for h in ads_roofing.headlines)
    assert all(len(d) <= AD_DESCRIPTION_MAX_CHARS for d in ads_roofing.descriptions)
    assert "Roof" in ads_roofing.lp_headline

    followup = client.draft_followup("Dallas County, Texas", motivated_seller.brand_name, facts)
    assert len(followup.sms_messages) == 2
    assert all(len(sms) <= SMS_MAX_CHARS for sms in followup.sms_messages)
    assert all(motivated_seller.brand_name in sms for sms in followup.sms_messages)
    assert all("STOP" in sms for sms in followup.sms_messages)
    assert len(followup.emails) == 2

    followup_empty = client.draft_followup("Dallas County, Texas", "Brand", [])
    assert "your Dallas property" in followup_empty.emails[0].body

    regen = client.regenerate_assets(
        county_name="Dallas County, Texas",
        brand_name="Example Home Buyers",
        failed_items=[
            ("headline_1", "Too long"),
            ("description_1", "Too long"),
            ("sms_1", "Missing STOP"),
            ("lp_consent_disclosure", "Missing automated"),
            ("lp_headline", "Fair Housing violation"),
            ("other_asset", "Unknown error"),
        ],
        vertical_config=motivated_seller,
    )
    regen_map = {item.item_id: item.text for item in regen.assets}
    assert len(regen_map["headline_1"]) <= AD_HEADLINE_MAX_CHARS
    assert len(regen_map["description_1"]) <= AD_DESCRIPTION_MAX_CHARS
    assert len(regen_map["sms_1"]) <= SMS_MAX_CHARS
    assert "STOP" in regen_map["sms_1"]
    assert "automated" in regen_map["lp_consent_disclosure"].lower()
    assert "not a condition" in regen_map["lp_consent_disclosure"].lower()
    assert "Example Home Buyers" in regen_map["lp_headline"]
    assert "Example Home Buyers" in regen_map["other_asset"]

    comp_with_pinellas = client.compare_counties(["Dallas 48113", "Pinellas 12103", "Cook 17031"])
    assert comp_with_pinellas.recommended_county_fips == DALLAS_FIPS
    assert "Pinellas County (12103)" in comp_with_pinellas.summary

    comp_without_pinellas = client.compare_counties(["Dallas 48113", "Cook 17031"])
    assert comp_without_pinellas.recommended_county_fips == DALLAS_FIPS
    assert "Pinellas County (12103)" not in comp_without_pinellas.summary


def test_fake_client_simulate_error_raises_llm_error() -> None:
    table = _county_table()
    dallas = table[DALLAS_FIPS]
    vertical = load_verticals_config().verticals["motivated_seller"]
    facts = _sample_facts()
    client = FakeModelClient(simulate_error=True)

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.interpret_triggers(dallas, vertical)

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.draft_qualification(dallas.county_name, vertical, facts)

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.draft_ads_and_lp(dallas.county_name, vertical, facts)

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.draft_followup(dallas.county_name, vertical.brand_name, facts)

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.regenerate_assets(
            dallas.county_name, vertical.brand_name, [("headline_1", "bad")], vertical
        )

    with pytest.raises(LlmError, match="Simulated LLM client failure"):
        client.compare_counties(["summary"])


def test_anthropic_client_all_methods_and_code_fence_stripping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _county_table()
    dallas = table[DALLAS_FIPS]
    vertical = load_verticals_config().verticals["motivated_seller"]
    facts = _sample_facts()

    sdk_client = anthropic.Anthropic(api_key="test-api-key")
    recorded_models: list[str] = []
    queued_responses: list[Message] = [
        _make_message(
            TriggerInterpretationOutput(
                triggers=[
                    TriggerItem(
                        claim="102 hail reports",
                        field="hail_reports_1in",
                        value=102,
                        source=NOAA_SOURCE,
                    )
                ]
            ).model_dump_json()
        ),
        _make_message(
            "```json\n"
            + QualificationQuestionsOutput(
                questions=[QualificationQuestionItem(question="How soon?", topic="timeline")]
            ).model_dump_json()
            + "\n```"
        ),
        _make_message(
            "```\n"
            + AdsAndLandingPageOutput(
                headlines=["Sell Dallas Home", "Cash Offer Options", "As-Is Sale"],
                descriptions=["Desc 1", "Desc 2"],
                lp_headline="LP Headline",
                lp_subheadline="LP Subheadline",
                cta_text="Submit",
                bullet_points=["Point 1"],
                consent_disclosure="Automated calls, not a condition, reply STOP.",
            ).model_dump_json()
            + "\n```",
            include_tool_use=True,
        ),
        _make_message(
            FollowupOutput(
                sms_messages=["Example Home Buyers: Hi. Reply STOP to opt out."],
                emails=[EmailItem(subject="Hello", body="Body")],
            ).model_dump_json()
        ),
        _make_message(
            RegenerateOutput(
                assets=[RegeneratedAssetItem(item_id="headline_1", text="Fixed Headline")]
            ).model_dump_json()
        ),
        _make_message(
            ComparisonOutput(
                recommended_county_fips=DALLAS_FIPS,
                summary="Dallas is best.",
            ).model_dump_json()
        ),
    ]

    def fake_create(*, model: str, **kwargs: Any) -> Message:
        _ = kwargs
        recorded_models.append(model)
        return queued_responses.pop(0)

    monkeypatch.setattr(sdk_client.messages, "create", fake_create)
    client = AnthropicModelClient(client=sdk_client)

    triggers_out = client.interpret_triggers(dallas, vertical)
    assert triggers_out.triggers[0].value == 102

    qual_out = client.draft_qualification(dallas.county_name, vertical, facts)
    assert qual_out.questions[0].topic == "timeline"

    ads_out = client.draft_ads_and_lp(dallas.county_name, vertical, facts)
    assert ads_out.lp_headline == "LP Headline"

    followup_out = client.draft_followup(dallas.county_name, vertical.brand_name, facts)
    assert len(followup_out.sms_messages) == 1

    regen_out = client.regenerate_assets(
        dallas.county_name, vertical.brand_name, [("headline_1", "Too long")], vertical
    )
    assert regen_out.assets[0].text == "Fixed Headline"

    comp_out = client.compare_counties(["Dallas summary"])
    assert comp_out.recommended_county_fips == DALLAS_FIPS

    assert recorded_models == [
        HAIKU_MODEL,
        HAIKU_MODEL,
        SONNET_MODEL,
        HAIKU_MODEL,
        SONNET_MODEL,
        SONNET_MODEL,
    ]


def test_anthropic_client_api_and_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise default SDK client construction when api_key is provided without explicit client.
    default_init_client = AnthropicModelClient(api_key="test-api-key")
    assert isinstance(default_init_client, AnthropicModelClient)

    sdk_client = anthropic.Anthropic(api_key="test-api-key")
    client = AnthropicModelClient(client=sdk_client)
    request = anthropic.DefaultHttpxClient().build_request(
        "POST", "https://api.anthropic.com/v1/messages"
    )

    for error in (
        anthropic.APIConnectionError(message="conn failed", request=request),
        httpx.ReadTimeout("timed out"),
        OSError("socket error"),
        TimeoutError("timeout"),
    ):

        def fake_create(*, exc: Exception = error, **kwargs: Any) -> Message:
            _ = kwargs
            raise exc

        monkeypatch.setattr(sdk_client.messages, "create", fake_create)
        with pytest.raises(LlmError, match="Anthropic API call failed"):
            client.compare_counties(["Dallas"])


def test_anthropic_client_empty_and_invalid_json_raises_llm_output_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_client = anthropic.Anthropic(api_key="test-api-key")
    client = AnthropicModelClient(client=sdk_client)

    def return_empty(**kwargs: Any) -> Message:
        _ = kwargs
        return _make_message(None, include_tool_use=True)

    monkeypatch.setattr(sdk_client.messages, "create", return_empty)
    with pytest.raises(LlmOutputError, match="returned no text blocks"):
        client.compare_counties(["Dallas"])

    def return_invalid_json(**kwargs: Any) -> Message:
        _ = kwargs
        return _make_message("{not valid json")

    monkeypatch.setattr(sdk_client.messages, "create", return_invalid_json)
    with pytest.raises(LlmOutputError, match="failed validation"):
        client.compare_counties(["Dallas"])

    def return_wrong_schema(**kwargs: Any) -> Message:
        _ = kwargs
        return _make_message('{"wrong_field": 123}')

    monkeypatch.setattr(sdk_client.messages, "create", return_wrong_schema)
    with pytest.raises(LlmOutputError, match="failed validation"):
        client.compare_counties(["Dallas"])

    # Test retry on validation error where second attempt succeeds
    attempts = 0

    def retry_then_succeed(**kwargs: Any) -> Message:
        nonlocal attempts
        attempts += 1
        _ = kwargs
        if attempts == 1:
            return _make_message("{broken json")
        return _make_message('{"recommended_county_fips": "48113", "summary": "Dallas"}')

    monkeypatch.setattr(sdk_client.messages, "create", retry_then_succeed)
    result = client.compare_counties(["Dallas"])
    assert result.recommended_county_fips == "48113"
    assert attempts == 2
