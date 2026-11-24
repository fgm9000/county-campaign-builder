"""Unit tests for scripts/smoke_test.py using FastAPI TestClient and httpx.MockTransport."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from county_campaign_builder.api import ACCESS_CODE_HEADER, create_app
from county_campaign_builder.graph import CampaignDependencies, create_default_dependencies
from county_campaign_builder.limits import StrictRateLimiter
from county_campaign_builder.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT_PATH = REPO_ROOT / "scripts" / "smoke_test.py"
TEST_CODE = "smoke-access-code"
BASE_URL = "https://smoke.example.run.app"


class _SmokeModule(Protocol):
    DEFAULT_COUNTY_FIPS: str
    SmokeTestError: type[RuntimeError]

    def parse_sse_events(self, lines: Iterable[str]) -> list[tuple[str, dict[str, object]]]:
        """Parse raw Server-Sent Events lines into event-name and payload tuples."""

    def run_smoke_tests(
        self,
        url: str,
        code: str | None = None,
        timeout: float = ...,
        *,
        live_mode: bool = True,
        client: httpx.Client | TestClient | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> list[str]:
        """Execute post-deploy health and live SSE smoke assertions."""

    def main(self, argv: Sequence[str] | None = None) -> int:
        """CLI entrypoint returning process exit status."""


def _load_smoke_module() -> _SmokeModule:
    spec = importlib.util.spec_from_file_location("smoke_test_script", SMOKE_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast("_SmokeModule", module)


SMOKE = _load_smoke_module()
SmokeTestError = SMOKE.SmokeTestError
DEFAULT_COUNTY_FIPS = SMOKE.DEFAULT_COUNTY_FIPS


def _valid_campaign_body(fips: str = DEFAULT_COUNTY_FIPS) -> dict[str, object]:
    return {
        "county_fips": fips,
        "county_name": "Dallas County, Texas",
        "vertical": "motivated_seller",
        "status": "success",
        "error_message": None,
        "facts": [],
        "corrections": [],
        "unit_economics": {
            "bid_per_lead_usd": 120.0,
            "cpl_best_usd": 30.0,
            "cpl_worst_usd": 83.33,
            "max_cpc_usd": 7.2,
            "verdict": "green",
            "explanation": "Viable economics.",
        },
        "assets": {
            "questions": [],
            "ad_copy": {"headlines": [], "descriptions": []},
            "landing_page": None,
            "sms_messages": [],
            "email_followups": [],
        },
        "needs_human_review": [],
    }


def _valid_sse_text(fips: str = DEFAULT_COUNTY_FIPS) -> str:
    progress = json.dumps({"fips": fips, "stage": "loading_data"})
    done = json.dumps(_valid_campaign_body(fips))
    return f"event: progress\ndata: {progress}\n\nevent: done\ndata: {done}\n\n"


def _mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = BASE_URL,
) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=base_url)


def _default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/v1/campaigns":
        if request.headers.get(ACCESS_CODE_HEADER) != TEST_CODE:
            return httpx.Response(401, json={"detail": "invalid or missing access code"})
        return httpx.Response(200, json=_valid_campaign_body())
    if request.url.path == "/v1/campaigns/stream":
        if request.headers.get(ACCESS_CODE_HEADER) != TEST_CODE:
            return httpx.Response(401, json={"detail": "invalid or missing access code"})
        return httpx.Response(
            200,
            content=_valid_sse_text().encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )
    return httpx.Response(404)


@pytest.fixture(scope="module")
def fake_deps() -> CampaignDependencies:
    return create_default_dependencies(Settings(fake_model=True))


def test_smoke_test_against_fastapi_live_auth_app(fake_deps: CampaignDependencies) -> None:
    app = create_app(
        settings=Settings(
            fake_model=False,
            anthropic_api_key=SecretStr("sk-ant-smoke-test"),
            live_access_code=SecretStr(TEST_CODE),
        ),
        deps=fake_deps,
        rate_limiter=StrictRateLimiter(100, 1000),
    )
    client = TestClient(app)

    summary = SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, live_mode=True, client=client)
    assert len(summary) == 4
    assert "[ok] /health" in summary[0]
    assert "401" in summary[1]
    assert "fips=48113" in summary[2]
    assert "ended with done" in summary[3]


def test_smoke_test_against_fastapi_fake_mode_app(fake_deps: CampaignDependencies) -> None:
    app = create_app(
        settings=Settings(fake_model=True),
        deps=fake_deps,
        rate_limiter=StrictRateLimiter(100, 1000),
    )
    client = TestClient(app)

    summary = SMOKE.run_smoke_tests(BASE_URL, code=None, live_mode=False, client=client)
    assert len(summary) == 3
    assert all("401" not in line for line in summary)


def test_smoke_test_passes_with_mock_transport_and_empty_base_url() -> None:
    client = httpx.Client(transport=httpx.MockTransport(_default_handler))
    summary = SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, live_mode=True, client=client)
    assert len(summary) == 4


def test_smoke_test_fails_when_health_returns_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(503, json={"status": "down"})
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="/health returned 503"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_health_payload_is_not_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "degraded"})
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="expected 'ok'"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_unauthenticated_request_is_not_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns" and ACCESS_CODE_HEADER not in request.headers:
            return httpx.Response(200, json=_valid_campaign_body())
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="expected 401"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_campaign_endpoint_returns_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.path == "/v1/campaigns"
            and request.headers.get(ACCESS_CODE_HEADER) == TEST_CODE
        ):
            return httpx.Response(502, json={"detail": "campaign_failed"})
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="/v1/campaigns returned 502"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_campaign_payload_is_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.path == "/v1/campaigns"
            and request.headers.get(ACCESS_CODE_HEADER) == TEST_CODE
        ):
            bad = _valid_campaign_body()
            bad["status"] = "failed"
            return httpx.Response(200, json=bad)
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="expected status='success'"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_campaign_response_is_non_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.path == "/v1/campaigns"
            and request.headers.get(ACCESS_CODE_HEADER) == TEST_CODE
        ):
            return httpx.Response(200, text="not-json")
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="not valid JSON"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_stream_has_wrong_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/stream":
            return httpx.Response(200, json={"status": "wrong"})
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="text/event-stream"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_stream_returns_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/stream":
            return httpx.Response(500, text="error")
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="/v1/campaigns/stream returned 500"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_stream_ends_with_error_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/stream":
            progress = json.dumps({"fips": DEFAULT_COUNTY_FIPS, "stage": "loading_data"})
            err = json.dumps({"error": "campaign_failed"})
            body = f"event: progress\ndata: {progress}\n\nevent: error\ndata: {err}\n\n"
            return httpx.Response(
                200,
                content=body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="ended with event 'error'"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_stream_does_not_start_with_progress() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/stream":
            done = json.dumps(_valid_campaign_body())
            body = f"event: done\ndata: {done}\n\n"
            return httpx.Response(
                200,
                content=body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="expected 'progress'"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_fails_when_stream_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/campaigns/stream":
            return httpx.Response(
                200,
                content=b"",
                headers={"content-type": "text/event-stream"},
            )
        return _default_handler(request)

    with pytest.raises(SmokeTestError, match="emitted no SSE events"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_smoke_test_wraps_http_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(SmokeTestError, match="HTTP request failed"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, client=_mock_client(handler))


def test_parse_sse_events_supports_comments_and_rejects_malformed() -> None:
    events = SMOKE.parse_sse_events([": keepalive", "event: ping", 'data: {"ok": true}', ""])
    assert events == [("ping", {"ok": True})]

    with pytest.raises(SmokeTestError, match="malformed SSE frame"):
        SMOKE.parse_sse_events(["event: orphan", ""])


def test_smoke_test_validates_arguments_and_main_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SmokeTestError, match="timeout must be positive"):
        SMOKE.run_smoke_tests(BASE_URL, code=TEST_CODE, timeout=0.0)

    with pytest.raises(SmokeTestError, match="--code is required"):
        SMOKE.run_smoke_tests(BASE_URL, code=None, live_mode=True)

    with pytest.raises(SmokeTestError, match="http:// or https://"):
        SMOKE.run_smoke_tests("ftp://invalid.example", code=TEST_CODE, live_mode=True)

    real_client_cls = httpx.Client
    captured_calls: list[dict[str, Any]] = []

    def make_ok_client(**kwargs: Any) -> httpx.Client:
        captured_calls.append(dict(kwargs))
        return real_client_cls(transport=httpx.MockTransport(_default_handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", make_ok_client)
    exit_code = SMOKE.main(["--url", f"{BASE_URL}/", "--code", TEST_CODE, "--timeout", "15"])
    assert exit_code == 0
    assert captured_calls[0]["base_url"] == BASE_URL
    assert captured_calls[0]["timeout"] == 15.0
    assert "[ok] /health" in capsys.readouterr().out

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    def make_failing_client(**kwargs: Any) -> httpx.Client:
        return real_client_cls(transport=httpx.MockTransport(failing_handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", make_failing_client)
    fail_code = SMOKE.main(["--url", BASE_URL, "--code", TEST_CODE])
    assert fail_code == 1
    assert "[fail]" in capsys.readouterr().err
