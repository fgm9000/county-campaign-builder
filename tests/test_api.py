"""Tests for the HTTP API: campaign endpoints (JSON and SSE), security, rate limits, and logs."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from county_campaign_builder.api import (
    ACCESS_CODE_HEADER,
    PROGRESS_STAGES,
    configure_logging,
    create_app,
    create_app_from_env,
)
from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.domain import VerticalConfig
from county_campaign_builder.graph import (
    CampaignDependencies,
    create_default_dependencies,
    run_campaign,
    run_multi_campaign,
)
from county_campaign_builder.limits import StrictRateLimiter
from county_campaign_builder.llm import (
    DALLAS_FIPS,
    PINELLAS_FIPS,
    FakeModelClient,
    LlmError,
    TriggerInterpretationOutput,
)
from county_campaign_builder.models import CampaignInput, MultiCountyInput, NumericRange
from county_campaign_builder.settings import Settings

TEST_ACCESS_CODE = "secret123"
TEST_ORIGIN = "https://fgm9000.github.io"


class FakeClock:
    """Deterministic clock for rate-limiter tests."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _FailingModelClient(FakeModelClient):
    """Fake model client whose trigger interpretation fails to test stream error handling."""

    def interpret_triggers(
        self,
        county: CountyRecord,
        vertical_config: VerticalConfig,
    ) -> TriggerInterpretationOutput:
        raise LlmError("simulated upstream failure")


@pytest.fixture(scope="module")
def deps() -> CampaignDependencies:
    return create_default_dependencies(Settings(fake_model=True))


def _live_settings() -> Settings:
    return Settings(
        fake_model=False,
        anthropic_api_key=SecretStr("sk-ant-test-key"),
        live_access_code=SecretStr(TEST_ACCESS_CODE),
    )


def _single_input(fips: str = DALLAS_FIPS) -> CampaignInput:
    return CampaignInput(
        county_fips=fips,
        vertical="motivated_seller",
        bid_per_lead_usd=120.0,
        cpc_usd=NumericRange(min=3.0, max=5.0),
        landing_cvr=NumericRange(min=0.06, max=0.10),
    )


def _multi_input(fips_list: list[str] | None = None) -> MultiCountyInput:
    return MultiCountyInput(
        county_fips_list=fips_list or [DALLAS_FIPS, PINELLAS_FIPS],
        vertical="motivated_seller",
        bid_per_lead_usd=120.0,
        cpc_usd=NumericRange(min=3.0, max=5.0),
        landing_cvr=NumericRange(min=0.06, max=0.10),
    )


def _make_client(
    deps: CampaignDependencies,
    *,
    settings: Settings | None = None,
    rate_limiter: StrictRateLimiter | None = None,
    failure_limiter: StrictRateLimiter | None = None,
) -> TestClient:
    app = create_app(
        settings=settings or Settings(fake_model=True),
        deps=deps,
        rate_limiter=rate_limiter or StrictRateLimiter(100, 1000, FakeClock()),
        failure_limiter=failure_limiter,
    )
    return TestClient(app)


def _parse_sse(raw_text: str) -> list[tuple[str, dict[str, object]]]:
    blocks = [block for block in raw_text.strip().split("\n\n") if block.strip()]
    events: list[tuple[str, dict[str, object]]] = []
    for block in blocks:
        lines = block.split("\n")
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        name = lines[0].removeprefix("event: ")
        payload = json.loads(lines[1].removeprefix("data: "))
        events.append((name, payload))
    return events


def test_health_returns_ok(deps: CampaignDependencies) -> None:
    client = _make_client(deps)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/healthz").json() == {"status": "ok"}

    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/docs"


def test_single_county_campaign_success(deps: CampaignDependencies) -> None:
    body = _single_input(DALLAS_FIPS)
    response = _make_client(deps).post("/v1/campaigns", json=body.model_dump(mode="json"))
    assert response.status_code == 200
    expected = json.loads(run_campaign(body, deps).model_dump_json())
    assert response.json() == expected
    assert response.json()["county_fips"] == DALLAS_FIPS
    assert response.json()["status"] == "success"


def test_single_county_invalid_fips_returns_422(deps: CampaignDependencies) -> None:
    body = _single_input("99999")
    response = _make_client(deps).post("/v1/campaigns", json=body.model_dump(mode="json"))
    assert response.status_code == 422
    assert response.json()["detail"] == "FIPS code '99999' not found in county table."


def test_multi_county_campaign_success(deps: CampaignDependencies) -> None:
    body = _multi_input([DALLAS_FIPS, PINELLAS_FIPS])
    response = _make_client(deps).post("/v1/campaigns", json=body.model_dump(mode="json"))
    assert response.status_code == 200
    expected = json.loads(run_multi_campaign(body, deps).model_dump_json())
    assert response.json() == expected
    assert len(response.json()["campaigns"]) == 2


def test_multi_county_invalid_fips_returns_422(deps: CampaignDependencies) -> None:
    body = _multi_input([DALLAS_FIPS, "99999"])
    response = _make_client(deps).post("/v1/campaigns", json=body.model_dump(mode="json"))
    assert response.status_code == 422
    assert response.json()["detail"] == "FIPS code '99999' not found in county table."


def test_live_mode_access_code_enforced(deps: CampaignDependencies) -> None:
    client = _make_client(deps, settings=_live_settings())
    payload = _single_input().model_dump(mode="json")

    for path in ("/v1/campaigns", "/v1/campaigns/stream"):
        missing = client.post(path, json=payload)
        assert missing.status_code == 401
        wrong = client.post(path, json=payload, headers={ACCESS_CODE_HEADER: "wrong-code"})
        assert wrong.status_code == 401

    ok_json = client.post(
        "/v1/campaigns",
        json=payload,
        headers={ACCESS_CODE_HEADER: TEST_ACCESS_CODE},
    )
    assert ok_json.status_code == 200

    ok_stream = client.post(
        "/v1/campaigns/stream",
        json=payload,
        headers={ACCESS_CODE_HEADER: TEST_ACCESS_CODE},
    )
    assert ok_stream.status_code == 200


def test_failed_access_codes_are_rate_limited_without_using_daily_quota(
    deps: CampaignDependencies,
) -> None:
    clock = FakeClock()
    client = _make_client(
        deps,
        settings=_live_settings(),
        rate_limiter=StrictRateLimiter(100, 1, clock),
        failure_limiter=StrictRateLimiter(5, 1000, clock),
    )
    payload = _single_input().model_dump(mode="json")
    attacker = {"X-Forwarded-For": "203.0.113.7", ACCESS_CODE_HEADER: "wrong"}

    statuses = [
        client.post("/v1/campaigns", json=payload, headers=attacker).status_code for _ in range(6)
    ]
    assert statuses == [401, 401, 401, 401, 401, 429]

    blocked = client.post("/v1/campaigns", json=payload, headers=attacker)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0

    owner = {"X-Forwarded-For": "198.51.100.9", ACCESS_CODE_HEADER: TEST_ACCESS_CODE}
    assert client.post("/v1/campaigns", json=payload, headers=owner).status_code == 200


def test_rate_limit_exceeded_returns_429_with_retry_after(deps: CampaignDependencies) -> None:
    clock = FakeClock()
    client = _make_client(deps, rate_limiter=StrictRateLimiter(2, 100, clock))
    payload = _single_input().model_dump(mode="json")

    assert client.post("/v1/campaigns", json=payload).status_code == 200
    assert client.post("/v1/campaigns", json=payload).status_code == 200

    limited = client.post("/v1/campaigns", json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) == 60

    clock.now += 61
    assert client.post("/v1/campaigns", json=payload).status_code == 200


def test_rate_limit_uses_last_forwarded_hop_and_daily_quota(deps: CampaignDependencies) -> None:
    clock = FakeClock()
    client = _make_client(deps, rate_limiter=StrictRateLimiter(1, 2, clock))
    payload = _single_input().model_dump(mode="json")

    first = client.post(
        "/v1/campaigns", json=payload, headers={"X-Forwarded-For": "6.6.6.6, 1.1.1.1"}
    )
    spoofed = client.post(
        "/v1/campaigns", json=payload, headers={"X-Forwarded-For": "7.7.7.7, 1.1.1.1"}
    )
    other = client.post(
        "/v1/campaigns", json=payload, headers={"X-Forwarded-For": "7.7.7.7, 2.2.2.2"}
    )
    daily_cap = client.post(
        "/v1/campaigns", json=payload, headers={"X-Forwarded-For": "7.7.7.7, 3.3.3.3"}
    )
    assert (first.status_code, spoofed.status_code, other.status_code, daily_cap.status_code) == (
        200,
        429,
        200,
        429,
    )
    assert int(daily_cap.headers["Retry-After"]) > 60


def test_stream_single_county_emits_progress_stages_and_done(deps: CampaignDependencies) -> None:
    body = _single_input(DALLAS_FIPS)
    response = _make_client(deps).post("/v1/campaigns/stream", json=body.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.endswith("\n\n")

    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["progress"] * len(PROGRESS_STAGES) + ["done"]
    assert [data["stage"] for _, data in events[:-1]] == list(PROGRESS_STAGES)
    assert {data["fips"] for _, data in events[:-1]} == {DALLAS_FIPS}
    expected = json.loads(run_campaign(body, deps).model_dump_json())
    assert events[-1][1] == expected


def test_stream_multi_county_emits_progress_and_done(deps: CampaignDependencies) -> None:
    body = _multi_input([DALLAS_FIPS, PINELLAS_FIPS])
    response = _make_client(deps).post("/v1/campaigns/stream", json=body.model_dump(mode="json"))
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"
    progress_events = events[:-1]
    assert all(name == "progress" for name, _ in progress_events)
    assert len(progress_events) == 2 * len(PROGRESS_STAGES)
    expected = json.loads(run_multi_campaign(body, deps).model_dump_json())
    assert events[-1][1] == expected


def test_stream_invalid_fips_returns_422(deps: CampaignDependencies) -> None:
    body = _single_input("99999")
    response = _make_client(deps).post("/v1/campaigns/stream", json=body.model_dump(mode="json"))
    assert response.status_code == 422


def test_stream_handles_pipeline_failure_with_error_event(deps: CampaignDependencies) -> None:
    failing_deps = replace(deps, model=_FailingModelClient())
    response = _make_client(failing_deps).post(
        "/v1/campaigns/stream",
        json=_single_input(DALLAS_FIPS).model_dump(mode="json"),
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["progress", "error"]
    assert events[0][1] == {"fips": DALLAS_FIPS, "stage": "loading_data"}
    assert events[1][1] == {"error": "campaign_failed"}
    assert "simulated upstream failure" not in response.text


def test_stream_handles_unhandled_exception_with_error_event(
    deps: CampaignDependencies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_input_data: CampaignInput, _deps: CampaignDependencies) -> object:
        raise RuntimeError("internal-secret-trace")

    monkeypatch.setattr("county_campaign_builder.api.run_campaign", _boom)
    response = _make_client(deps).post(
        "/v1/campaigns/stream",
        json=_single_input(DALLAS_FIPS).model_dump(mode="json"),
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["progress", "error"]
    assert events[1][1] == {"error": "campaign_failed"}
    assert "internal-secret-trace" not in response.text


def test_post_campaigns_handles_unhandled_exception_with_502(
    deps: CampaignDependencies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_input_data: CampaignInput, _deps: CampaignDependencies) -> object:
        raise RuntimeError("internal-secret-trace")

    monkeypatch.setattr("county_campaign_builder.api.run_campaign", _boom)
    response = _make_client(deps).post(
        "/v1/campaigns",
        json=_single_input(DALLAS_FIPS).model_dump(mode="json"),
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "campaign_failed"}


def test_cors_middleware_config_and_exposed_headers(deps: CampaignDependencies) -> None:
    client = _make_client(deps)
    preflight = client.options(
        "/v1/campaigns",
        headers={
            "Origin": TEST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-access-code",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == TEST_ORIGIN
    assert ACCESS_CODE_HEADER in preflight.headers["access-control-allow-headers"]
    assert "DELETE" not in preflight.headers["access-control-allow-methods"]

    foreign = client.options(
        "/v1/campaigns",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in foreign.headers

    health = client.get("/health", headers={"Origin": TEST_ORIGIN})
    assert "retry-after" in health.headers["access-control-expose-headers"].lower()


def test_logs_are_single_line_json_without_secrets_or_pii(
    deps: CampaignDependencies,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _make_client(deps, settings=_live_settings())
    headers = {ACCESS_CODE_HEADER: TEST_ACCESS_CODE, "X-Forwarded-For": "8.8.4.4"}
    with caplog.at_level(logging.INFO, logger="county_campaign_builder"):
        client.post(
            "/v1/campaigns",
            json=_single_input(DALLAS_FIPS).model_dump(mode="json"),
            headers=headers,
        )
        client.post(
            "/v1/campaigns/stream",
            json=_multi_input([DALLAS_FIPS, PINELLAS_FIPS]).model_dump(mode="json"),
            headers=headers,
        )
        client.post(
            "/v1/campaigns",
            json=_single_input(DALLAS_FIPS).model_dump(mode="json"),
            headers={ACCESS_CODE_HEADER: "bad"},
        )
        client.post(
            "/v1/campaigns",
            json=_single_input("99999").model_dump(mode="json"),
            headers=headers,
        )

    records = [json.loads(record.getMessage()) for record in caplog.records]
    assert [record["event"] for record in records] == [
        "campaign_ok",
        "campaign_ok",
        "access_denied",
        "fips_rejected",
    ]
    first = records[0]
    assert first.keys() >= {
        "event",
        "status_code",
        "mode",
        "latency_ms",
        "county_fips",
        "vertical",
        "campaign_status",
        "facts",
        "corrections",
        "human_review_items",
        "verdict",
    }
    assert first["mode"] == "live"
    assert first["county_fips"] == DALLAS_FIPS
    assert first["vertical"] == "motivated_seller"
    assert all("\n" not in record.getMessage() for record in caplog.records)

    for forbidden in (TEST_ACCESS_CODE, "sk-ant-test-key", "8.8.4.4"):
        assert forbidden not in caplog.text


def test_create_app_from_env_and_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "LIVE_ACCESS_CODE", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FAKE_MODEL", "1")

    client = TestClient(create_app_from_env())
    assert client.get("/health").json() == {"status": "ok"}
    assert (
        client.post(
            "/v1/campaigns", json=_single_input(DALLAS_FIPS).model_dump(mode="json")
        ).status_code
        == 200
    )

    api_logger = logging.getLogger("county_campaign_builder")
    configure_logging()
    count = len(api_logger.handlers)
    configure_logging()
    assert count >= 1
    assert len(api_logger.handlers) == count
    assert api_logger.level == logging.INFO
