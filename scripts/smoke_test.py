"""Post-deploy smoke test CLI for county-campaign-builder Cloud Run and local instances."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Final, Protocol

import httpx

DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0
ACCESS_CODE_HEADER: Final[str] = "X-Access-Code"
DEFAULT_COUNTY_FIPS: Final[str] = "48113"
VALID_VERDICTS: Final[frozenset[str]] = frozenset({"green", "yellow", "red"})

DEFAULT_PAYLOAD: Final[dict[str, object]] = {
    "county_fips": DEFAULT_COUNTY_FIPS,
    "vertical": "motivated_seller",
    "bid_per_lead_usd": 120.0,
    "cpc_usd": {"min": 3.0, "max": 5.0},
    "landing_cvr": {"min": 0.06, "max": 0.10},
}


class SmokeTestError(RuntimeError):
    """Raised when a smoke test check fails."""


class HttpClient(Protocol):
    """Minimal structural interface shared by ``httpx.Client`` and ``TestClient``."""

    @property
    def base_url(self) -> httpx.URL:
        """Base URL configured on the client, if any."""

    def get(self, url: str) -> httpx.Response:
        """Send an HTTP GET request."""

    def post(
        self,
        url: str,
        *,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send an HTTP POST request."""

    def stream(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AbstractContextManager[httpx.Response]:
        """Open a streaming HTTP request context."""


def _resolve_target(client: HttpClient, base_url: str, path: str) -> str:
    if str(client.base_url):
        return path
    return f"{base_url.rstrip('/')}{path}"


def _parse_json_object(response: httpx.Response, context: str) -> dict[str, object]:
    try:
        decoded = response.json()
    except ValueError as exc:
        raise SmokeTestError(f"{context}: response body is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SmokeTestError(f"{context}: expected JSON object, got {type(decoded).__name__}")
    return {str(key): value for key, value in decoded.items()}


def validate_campaign_payload(data: object, expected_fips: str, context: str) -> None:
    """Validate that a parsed JSON object has the expected CountyCampaign structure."""
    if not isinstance(data, dict):
        raise SmokeTestError(f"{context}: expected JSON object, got {type(data).__name__}")
    if data.get("county_fips") != expected_fips:
        raise SmokeTestError(
            f"{context}: expected county_fips={expected_fips!r}, got {data.get('county_fips')!r}"
        )
    if data.get("status") != "success":
        raise SmokeTestError(f"{context}: expected status='success', got {data.get('status')!r}")
    economics = data.get("unit_economics")
    if not isinstance(economics, dict) or economics.get("verdict") not in VALID_VERDICTS:
        raise SmokeTestError(f"{context}: missing or invalid unit_economics")
    if not isinstance(data.get("assets"), dict):
        raise SmokeTestError(f"{context}: missing assets object")


def parse_sse_events(lines: Iterable[str]) -> list[tuple[str, dict[str, object]]]:
    """Parse SSE text lines into ``(event_name, json_payload)`` pairs."""
    events: list[tuple[str, dict[str, object]]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if event_name is None and not data_lines:
            return
        if event_name is None or not data_lines:
            raise SmokeTestError(
                f"malformed SSE frame (event={event_name!r}, data_lines={len(data_lines)})"
            )
        raw_data = "\n".join(data_lines)
        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise SmokeTestError(f"invalid JSON in SSE '{event_name}' event: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SmokeTestError(f"expected JSON object in SSE '{event_name}' event")
        events.append((event_name, {str(key): value for key, value in parsed.items()}))
        event_name = None
        data_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            flush()
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())

    flush()
    return events


def check_health(client: HttpClient, base_url: str) -> None:
    """Verify ``GET /health`` returns HTTP 200 and ``{"status": "ok"}``."""
    response = client.get(_resolve_target(client, base_url, "/health"))
    if response.status_code != 200:
        raise SmokeTestError(f"/health returned {response.status_code}, expected 200")
    body = _parse_json_object(response, "/health")
    if body.get("status") != "ok":
        raise SmokeTestError(f"/health returned status={body.get('status')!r}, expected 'ok'")


def check_unauthenticated_rejected(
    client: HttpClient,
    base_url: str,
    payload: Mapping[str, object],
) -> None:
    """Verify ``POST /v1/campaigns`` without an access code returns HTTP 401 in live mode."""
    response = client.post(
        _resolve_target(client, base_url, "/v1/campaigns"),
        json=dict(payload),
    )
    if response.status_code != 401:
        raise SmokeTestError(
            f"/v1/campaigns without access code returned {response.status_code}, expected 401"
        )


def check_campaign_run(
    client: HttpClient,
    base_url: str,
    payload: Mapping[str, object],
    headers: Mapping[str, str],
) -> dict[str, object]:
    """Verify ``POST /v1/campaigns`` returns HTTP 200 and a valid campaign payload."""
    response = client.post(
        _resolve_target(client, base_url, "/v1/campaigns"),
        json=dict(payload),
        headers=dict(headers),
    )
    if response.status_code != 200:
        raise SmokeTestError(f"/v1/campaigns returned {response.status_code}, expected 200")
    data = _parse_json_object(response, "/v1/campaigns")
    validate_campaign_payload(data, str(payload["county_fips"]), "/v1/campaigns")
    return data


def check_campaign_stream(
    client: HttpClient,
    base_url: str,
    payload: Mapping[str, object],
    headers: Mapping[str, str],
) -> list[tuple[str, dict[str, object]]]:
    """Verify ``POST /v1/campaigns/stream`` emits SSE progress events and ends with ``done``."""
    target = _resolve_target(client, base_url, "/v1/campaigns/stream")
    with client.stream("POST", target, json=dict(payload), headers=dict(headers)) as response:
        if response.status_code != 200:
            raise SmokeTestError(
                f"/v1/campaigns/stream returned {response.status_code}, expected 200"
            )
        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith("text/event-stream"):
            raise SmokeTestError(
                f"/v1/campaigns/stream returned content-type={content_type!r}, "
                "expected 'text/event-stream'"
            )
        events = parse_sse_events(response.iter_lines())

    if not events:
        raise SmokeTestError("/v1/campaigns/stream emitted no SSE events")
    if events[0][0] != "progress":
        raise SmokeTestError(
            f"/v1/campaigns/stream started with event {events[0][0]!r}, expected 'progress'"
        )
    if events[-1][0] != "done":
        raise SmokeTestError(
            f"/v1/campaigns/stream ended with event {events[-1][0]!r}, expected 'done'"
        )
    validate_campaign_payload(
        events[-1][1],
        str(payload["county_fips"]),
        "/v1/campaigns/stream done",
    )
    return events


def run_smoke_tests(
    url: str,
    code: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    *,
    live_mode: bool = True,
    client: HttpClient | None = None,
    payload: Mapping[str, object] | None = None,
) -> list[str]:
    """Execute the full smoke test sequence and return human-readable status lines."""
    if timeout <= 0:
        raise SmokeTestError(f"timeout must be positive, got {timeout}")
    if live_mode and not code:
        raise SmokeTestError("--code is required when live mode is enabled")

    request_payload: Mapping[str, object] = payload if payload is not None else DEFAULT_PAYLOAD
    headers: dict[str, str] = {ACCESS_CODE_HEADER: code} if code else {}
    summary: list[str] = []

    def execute(active_client: HttpClient) -> None:
        check_health(active_client, url)
        summary.append('[ok] /health -> 200 {"status": "ok"}')

        if live_mode:
            check_unauthenticated_rejected(active_client, url, request_payload)
            summary.append("[ok] /v1/campaigns (unauthenticated) -> 401")

        campaign = check_campaign_run(active_client, url, request_payload, headers)
        economics = campaign["unit_economics"]
        verdict = economics.get("verdict") if isinstance(economics, dict) else "unknown"
        summary.append(
            f"[ok] /v1/campaigns -> 200 (fips={campaign.get('county_fips')}, verdict={verdict})"
        )

        events = check_campaign_stream(active_client, url, request_payload, headers)
        summary.append(f"[ok] /v1/campaigns/stream -> 200 ({len(events)} events, ended with done)")

    try:
        if client is not None:
            execute(client)
        else:
            normalized = url.rstrip("/")
            if not normalized.startswith(("http://", "https://")):
                raise SmokeTestError(f"--url must start with http:// or https://, got {url!r}")
            with httpx.Client(base_url=normalized, timeout=timeout) as managed_client:
                execute(managed_client)
    except httpx.HTTPError as exc:
        raise SmokeTestError(f"HTTP request failed: {exc}") from exc

    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the smoke test runner."""
    parser = argparse.ArgumentParser(
        description="Run post-deploy smoke checks against a county-campaign-builder instance."
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the target service (for example https://service.run.app).",
    )
    parser.add_argument(
        "--code",
        default=None,
        help="Access code sent via the X-Access-Code header for authenticated endpoints.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--fake-mode",
        action="store_true",
        default=False,
        help="Skip the 401 unauthenticated check for servers running with FAKE_MODEL=1.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns 0 when all smoke checks pass and 1 on any failure."""
    args = parse_args(argv)
    try:
        summary = run_smoke_tests(
            url=args.url,
            code=args.code,
            timeout=args.timeout,
            live_mode=not args.fake_mode,
        )
    except SmokeTestError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
