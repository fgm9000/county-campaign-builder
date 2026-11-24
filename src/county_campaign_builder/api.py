"""HTTP API: campaign endpoints (JSON and SSE), access control, rate limiting, and JSON logs."""

import hmac
import json
import logging
import time
from collections.abc import Iterator, Mapping
from typing import Annotated, NoReturn

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from county_campaign_builder.county_data import CountyRecord
from county_campaign_builder.graph import (
    CampaignDependencies,
    create_default_dependencies,
    run_campaign,
    run_multi_campaign,
)
from county_campaign_builder.limits import StrictRateLimiter, client_ip
from county_campaign_builder.models import (
    CampaignComparison,
    CampaignInput,
    CountyCampaign,
    MultiCountyInput,
)
from county_campaign_builder.settings import Settings

LOGGER_NAME = "county_campaign_builder"
ACCESS_CODE_HEADER = "X-Access-Code"
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_BAD_GATEWAY = 502
STREAM_ERROR_MESSAGE = "campaign_failed"
# Failed access codes use a dedicated per-IP limiter so brute-force guesses cannot consume the
# global daily quota of legitimate live traffic.
MAX_FAILED_CODES_PER_MINUTE = 5
FAILED_CODES_DAILY_CAP = 1_000_000
PROGRESS_STAGES: tuple[str, ...] = (
    "loading_data",
    "interpreting_triggers",
    "verifying_numbers",
    "drafting_copy",
    "checking_compliance",
    "computing_economics",
)

CampaignRequest = CampaignInput | MultiCountyInput
CampaignResponse = CountyCampaign | CampaignComparison

logger = logging.getLogger(LOGGER_NAME)


def log_event(
    event: str,
    status_code: int,
    mode: str,
    started: float | None = None,
    request: CampaignRequest | None = None,
    result: CampaignResponse | None = None,
) -> None:
    """Emit one single-line structured JSON log record without PII or raw secrets."""
    payload: dict[str, object] = {
        "event": event,
        "status_code": status_code,
        "mode": mode,
    }
    if started is not None:
        payload["latency_ms"] = round((time.monotonic() - started) * 1000)
    if request is not None:
        county_fips: str | list[str] = (
            request.county_fips
            if isinstance(request, CampaignInput)
            else list(request.county_fips_list)
        )
        payload.update({"county_fips": county_fips, "vertical": request.vertical})
    if isinstance(result, CountyCampaign):
        payload.update(
            {
                "campaign_status": result.status,
                "facts": len(result.facts),
                "corrections": len(result.corrections),
                "human_review_items": len(result.needs_human_review),
                "verdict": result.unit_economics.verdict,
            }
        )
        if result.error_message:
            payload["error_message"] = result.error_message
    elif isinstance(result, CampaignComparison):
        payload.update(
            {
                "campaigns": len(result.campaigns),
                "recommended_county_fips": result.recommended_county_fips,
            }
        )
    logger.info(json.dumps(payload))


class RequestGuard:
    """Protections for campaign routes: live access code, per-IP rate limit, and FIPS check."""

    def __init__(
        self,
        settings: Settings,
        limiter: StrictRateLimiter,
        failure_limiter: StrictRateLimiter,
    ) -> None:
        self.mode = "fake" if settings.fake_model else "live"
        self._is_live = not settings.fake_model
        code = settings.live_access_code
        self._expected_code = code.get_secret_value().encode("utf-8") if code else None
        self._limiter = limiter
        self._failure_limiter = failure_limiter

    def authorize(
        self,
        request: Request,
        x_access_code: Annotated[str | None, Header()] = None,
    ) -> None:
        """FastAPI dependency: enforce live access code and per-IP/daily rate limits."""
        peer = request.client.host if request.client else None
        key = client_ip(request.headers.get("x-forwarded-for"), peer)
        if self._is_live and not self._code_is_valid(x_access_code):
            self._reject_bad_code(key)
        decision = self._limiter.check(key)
        if not decision.is_allowed:
            self._raise_rate_limited(decision.retry_after_seconds)

    def check_fips(
        self,
        body: CampaignRequest,
        county_table: Mapping[str, CountyRecord],
    ) -> None:
        """Validate that every requested FIPS code exists in the authoritative county table."""
        fips_list = [body.county_fips] if isinstance(body, CampaignInput) else body.county_fips_list
        for fips in fips_list:
            if fips not in county_table:
                log_event("fips_rejected", HTTP_UNPROCESSABLE, self.mode, request=body)
                raise HTTPException(
                    status_code=HTTP_UNPROCESSABLE,
                    detail=f"FIPS code '{fips}' not found in county table.",
                )

    def _reject_bad_code(self, key: str) -> NoReturn:
        decision = self._failure_limiter.check(key)
        if not decision.is_allowed:
            self._raise_rate_limited(decision.retry_after_seconds)
        log_event("access_denied", HTTP_UNAUTHORIZED, self.mode)
        raise HTTPException(
            status_code=HTTP_UNAUTHORIZED,
            detail="invalid or missing access code",
        )

    def _raise_rate_limited(self, retry_after_seconds: int) -> NoReturn:
        log_event("rate_limited", HTTP_TOO_MANY_REQUESTS, self.mode)
        raise HTTPException(
            status_code=HTTP_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after_seconds)},
        )

    def _code_is_valid(self, provided: str | None) -> bool:
        if provided is None or self._expected_code is None:
            return False
        return hmac.compare_digest(provided.encode("utf-8"), self._expected_code)


def _frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _progress_frame(fips: str, stage: str) -> str:
    return _frame("progress", json.dumps({"fips": fips, "stage": stage}))


def _execute_campaign(body: CampaignRequest, deps: CampaignDependencies) -> CampaignResponse:
    if isinstance(body, CampaignInput):
        return run_campaign(body, deps)
    return run_multi_campaign(body, deps)


def _has_fatal_pipeline_failure(result: CampaignResponse) -> bool:
    if isinstance(result, CountyCampaign):
        return result.status == "failed"
    return bool(result.campaigns) and all(c.status == "failed" for c in result.campaigns)


def _stream_frames(
    deps: CampaignDependencies,
    body: CampaignRequest,
    mode: str,
) -> Iterator[str]:
    started = time.monotonic()
    fips_list = [body.county_fips] if isinstance(body, CampaignInput) else body.county_fips_list
    for fips in fips_list:
        yield _progress_frame(fips, PROGRESS_STAGES[0])

    try:
        result = _execute_campaign(body, deps)
    except Exception:
        log_event("campaign_failed", 200, mode, started, body)
        yield _frame("error", json.dumps({"error": STREAM_ERROR_MESSAGE}))
        return

    if _has_fatal_pipeline_failure(result):
        log_event("campaign_failed", 200, mode, started, body, result)
        yield _frame("error", json.dumps({"error": STREAM_ERROR_MESSAGE}))
        return

    for fips in fips_list:
        for stage in PROGRESS_STAGES[1:]:
            yield _progress_frame(fips, stage)

    log_event("campaign_ok", 200, mode, started, body, result)
    yield _frame("done", result.model_dump_json())


def _register_basic_routes(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health")
    @app.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}


def _register_campaign_routes(
    app: FastAPI,
    deps: CampaignDependencies,
    guard: RequestGuard,
) -> None:
    guarded = Depends(guard.authorize)

    @app.post("/v1/campaigns", response_model=None)
    def create_campaign(
        body: CampaignRequest,
        _: Annotated[None, guarded],
    ) -> CampaignResponse | JSONResponse:
        guard.check_fips(body, deps.county_table)
        started = time.monotonic()
        try:
            result = _execute_campaign(body, deps)
        except Exception:
            log_event("campaign_failed", HTTP_BAD_GATEWAY, guard.mode, started, body)
            return JSONResponse(
                {"detail": STREAM_ERROR_MESSAGE},
                status_code=HTTP_BAD_GATEWAY,
            )
        log_event("campaign_ok", 200, guard.mode, started, body, result)
        return result

    @app.post("/v1/campaigns/stream", response_class=StreamingResponse)
    def stream_campaign_events(
        body: CampaignRequest,
        _: Annotated[None, guarded],
    ) -> StreamingResponse:
        guard.check_fips(body, deps.county_table)
        return StreamingResponse(
            _stream_frames(deps, body, guard.mode),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


def create_app(
    settings: Settings | None = None,
    deps: CampaignDependencies | None = None,
    rate_limiter: StrictRateLimiter | None = None,
    failure_limiter: StrictRateLimiter | None = None,
) -> FastAPI:
    """Application factory; configures CORS, access control, rate limits, and campaign routes."""
    resolved_settings = settings if settings is not None else Settings()
    resolved_deps = deps if deps is not None else create_default_dependencies(resolved_settings)
    limiter = rate_limiter or StrictRateLimiter(
        per_minute=resolved_settings.rate_limit_per_minute,
        daily_quota=resolved_settings.daily_quota,
    )
    failures = failure_limiter or StrictRateLimiter(
        per_minute=MAX_FAILED_CODES_PER_MINUTE,
        daily_quota=FAILED_CODES_DAILY_CAP,
    )
    guard = RequestGuard(resolved_settings, limiter, failures)
    app = FastAPI(title="county-campaign-builder")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", ACCESS_CODE_HEADER],
        expose_headers=["Retry-After"],
    )
    _register_basic_routes(app)
    _register_campaign_routes(app, resolved_deps, guard)
    return app


def configure_logging() -> None:
    """Send single-line JSON log records to stderr without duplicating handlers."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_app_from_env() -> FastAPI:
    """Entry point for ``uvicorn --factory``: read settings from the environment."""
    configure_logging()
    return create_app()
