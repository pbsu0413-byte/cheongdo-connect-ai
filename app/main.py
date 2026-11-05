"""청도 돌봄 도우미 API. 화면(정적 파일)과 API를 한 서비스로 제공한다."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agents, gate
from .masking import mask_personal_data
from .schemes import load_samples, load_schemes, scheme_by_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("care.api")

MAX_MEMO_CHARS = 4000
DISCLAIMER = "시연용 가상 데이터입니다. 실제 자격 판정이 아니며, AI가 만든 결과는 담당자가 확인해야 합니다."
KST = timezone(timedelta(hours=9))
STATIC_DIR = Path(__file__).resolve().parent / "static"
_last_model_status: str | None = None


def _record_model_result(is_fallback: bool) -> None:
    global _last_model_status
    _last_model_status = "last_call_failed" if is_fallback else "last_call_success"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작을 막지 않도록 백그라운드 스레드에서 Copilot 런타임을 미리 내려받는다.
    asyncio.get_running_loop().run_in_executor(None, agents.warm_up_runtime)
    yield


app = FastAPI(title="청도 돌봄 도우미", docs_url=None, redoc_url=None, lifespan=lifespan)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# 공개 데모의 Copilot 사용량과 서버 자원을 지키기 위한 호출 제한(인스턴스 단위, 메모리 기반).
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))
MAX_CONCURRENT_MODEL_CALLS = int(os.environ.get("MAX_CONCURRENT_MODEL_CALLS", "3"))
SLOT_WAIT_SECONDS = 25
_model_slots = asyncio.Semaphore(MAX_CONCURRENT_MODEL_CALLS)
_recent_calls: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _check_rate_limit(request: Request) -> None:
    now = time.monotonic()
    calls = _recent_calls[_client_key(request)]
    while calls and now - calls[0] > 60:
        calls.popleft()
    if len(calls) >= RATE_LIMIT_PER_MINUTE:
        raise _error(429, "rate_limited", "요청이 너무 많습니다. 1분 뒤에 다시 시도해 주세요.")
    calls.append(now)


@asynccontextmanager
async def _model_slot():
    try:
        await asyncio.wait_for(_model_slots.acquire(), timeout=SLOT_WAIT_SECONDS)
    except asyncio.TimeoutError:
        raise _error(503, "busy", "지금 요청이 몰려 있습니다. 잠시 후 다시 시도해 주세요.") from None
    try:
        yield
    finally:
        _model_slots.release()


@app.exception_handler(HTTPException)
async def http_error_handler(_request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


class MaskRequest(BaseModel):
    text: str = Field(default="")


class MatchRequest(BaseModel):
    masked_text: str = Field(default="")
    mask_token: str = Field(default="")


class DraftRequest(BaseModel):
    masked_text: str = Field(default="")
    mask_token: str = Field(default="")
    scheme_id: str = Field(default="")


class ApproveRequest(BaseModel):
    draft_text: str = Field(default="")
    scheme_id: str = Field(default="")
    draft_token: str = Field(default="")


class ReviewRequest(BaseModel):
    masked_text: str = Field(default="")
    mask_token: str = Field(default="")
    scheme_id: str = Field(default="")
    draft_text: str = Field(default="")


def _require_confirmed(masked_text: str, mask_token: str) -> None:
    if not masked_text.strip():
        raise _error(400, "empty_input", "마스킹 결과가 비어 있습니다.")
    if not mask_token or not gate.verify_token(mask_token, "mask", gate.text_hash(masked_text)):
        raise _error(403, "confirmation_required", "마스킹 결과를 확인한 뒤에만 진행할 수 있습니다. 처음부터 다시 시도해 주세요.")


@app.get("/api/health")
async def health() -> dict[str, str]:
    model_status = _last_model_status or "not_checked"
    return {"status": "ok", "model_status": model_status}


@app.get("/api/samples")
async def samples() -> dict:
    return load_samples()


@app.get("/api/schemes")
async def schemes() -> dict:
    return load_schemes()


@app.post("/api/mask")
async def mask(request: MaskRequest) -> dict:
    text = request.text.strip()
    if not text:
        raise _error(400, "empty_input", "메모를 입력하거나 샘플을 선택해 주세요.")
    if len(text) > MAX_MEMO_CHARS:
        raise _error(400, "too_long", f"메모는 {MAX_MEMO_CHARS}자 이하로 입력해 주세요.")
    result = mask_personal_data(text)
    return {
        "masked_text": result.masked_text,
        "counts": result.counts,
        "warnings": result.warnings,
        "mask_token": gate.issue_token("mask", gate.text_hash(result.masked_text)),
        "limitations": "이름과 주소는 규칙 기반이라 놓치거나 과하게 가릴 수 있습니다. 직접 확인해 주세요. 질병명·소득 같은 민감 정보는 가리지 않습니다.",
    }


@app.post("/api/match")
async def match(request: MatchRequest, http_request: Request) -> dict:
    _require_confirmed(request.masked_text, request.mask_token)
    _check_rate_limit(http_request)
    started = time.monotonic()
    async with _model_slot():
        result = await agents.match_schemes(request.masked_text)
    _record_model_result(result["is_fallback"])
    logger.info("match done fallback=%s candidates=%d ms=%d", result["is_fallback"], len(result["candidates"]), (time.monotonic() - started) * 1000)
    return {
        **result,
        "ai_generated": not result["is_fallback"],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "disclaimer": DISCLAIMER,
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/draft/stream")
async def draft_stream(request: DraftRequest, http_request: Request) -> StreamingResponse:
    _require_confirmed(request.masked_text, request.mask_token)
    if request.scheme_id not in scheme_by_id():
        raise _error(400, "unknown_scheme", "존재하지 않는 제도입니다. 후보 목록에서 선택해 주세요.")
    _check_rate_limit(http_request)
    try:
        await asyncio.wait_for(_model_slots.acquire(), timeout=SLOT_WAIT_SECONDS)
    except asyncio.TimeoutError:
        raise _error(503, "busy", "지금 요청이 몰려 있습니다. 잠시 후 다시 시도해 주세요.") from None

    async def events():
        try:
            started = time.monotonic()
            yield _sse("status", {"message": "마스킹된 메모와 제도 항목을 Copilot 에이전트에 전달했습니다."})
            async for item in agents.stream_draft(request.masked_text, request.scheme_id):
                if item["type"] == "delta":
                    yield _sse("delta", {"text": item["text"]})
                elif item["type"] == "reset":
                    yield _sse("reset", {})
                else:
                    payload = {
                        "draft": item["draft"],
                        "is_fallback": item["is_fallback"],
                        "engine": item["engine"],
                        "scheme_id": request.scheme_id,
                        "ai_generated": not item["is_fallback"],
                        "status": "draft",
                        "draft_token": gate.issue_token("draft", request.scheme_id),
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "disclaimer": DISCLAIMER,
                    }
                    _record_model_result(item["is_fallback"])
                    logger.info("draft stream done fallback=%s ms=%d", item["is_fallback"], payload["elapsed_ms"])
                    yield _sse("done", payload)
        finally:
            _model_slots.release()

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/review")
async def review(request: ReviewRequest, http_request: Request) -> dict:
    _require_confirmed(request.masked_text, request.mask_token)
    if request.scheme_id not in scheme_by_id():
        raise _error(400, "unknown_scheme", "존재하지 않는 제도입니다.")
    if not request.draft_text.strip() or len(request.draft_text) > MAX_MEMO_CHARS * 2:
        raise _error(400, "invalid_draft", "점검할 초안이 없거나 너무 깁니다.")
    _check_rate_limit(http_request)
    async with _model_slot():
        result = await agents.review_draft(request.masked_text, request.scheme_id, request.draft_text)
    _record_model_result(result["is_fallback"])
    return {**result, "ai_generated": not result["is_fallback"], "disclaimer": DISCLAIMER}


@app.post("/api/draft")
async def draft(request: DraftRequest, http_request: Request) -> dict:
    _require_confirmed(request.masked_text, request.mask_token)
    if request.scheme_id not in scheme_by_id():
        raise _error(400, "unknown_scheme", "존재하지 않는 제도입니다. 후보 목록에서 선택해 주세요.")
    _check_rate_limit(http_request)
    started = time.monotonic()
    async with _model_slot():
        result = await agents.draft_application(request.masked_text, request.scheme_id)
    _record_model_result(result["is_fallback"])
    logger.info("draft done fallback=%s ms=%d", result["is_fallback"], (time.monotonic() - started) * 1000)
    return {
        **result,
        "scheme_id": request.scheme_id,
        "ai_generated": not result["is_fallback"],
        "status": "draft",
        "draft_token": gate.issue_token("draft", request.scheme_id),
        "disclaimer": DISCLAIMER,
    }


@app.post("/api/approve")
async def approve(request: ApproveRequest) -> dict:
    if not request.draft_text.strip():
        raise _error(400, "empty_input", "승인할 초안이 비어 있습니다.")
    if request.scheme_id not in scheme_by_id() or not gate.verify_token(request.draft_token, "draft", request.scheme_id):
        raise _error(403, "draft_required", "초안을 만든 뒤에만 승인할 수 있습니다.")
    return {"status": "approved", "approved_at": datetime.now(KST).isoformat(timespec="seconds"), "disclaimer": DISCLAIMER}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
