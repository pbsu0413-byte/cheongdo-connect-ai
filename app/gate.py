"""서버가 단계 순서를 강제하기 위한 서명 토큰. 토큰에는 원문이나 개인정보를 넣지 않는다."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

TOKEN_TTL_SECONDS = 30 * 60

_signing_key: bytes | None = None


def _key() -> bytes:
    global _signing_key
    if _signing_key is None:
        configured = os.environ.get("SIGNING_KEY")
        _signing_key = configured.encode() if configured else secrets.token_bytes(32)
    return _signing_key


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(stage: str, subject: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = json.dumps({"s": stage, "h": subject, "e": int(time.time()) + ttl}, separators=(",", ":"))
    body = _b64(payload.encode())
    signature = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_token(token: str, stage: str, subject: str) -> bool:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    return (
        payload.get("s") == stage
        and hmac.compare_digest(str(payload.get("h")), subject)
        and int(payload.get("e", 0)) >= time.time()
    )
