import pytest
from fastapi.testclient import TestClient

from app import agents, main
from app.masking import mask_personal_data

client = TestClient(main.app)


def masked_flow(text="홍길순 어르신 연락처 010-0000-0001. 혼자 거주하며 전기요금 3개월 체납."):
    return client.post("/api/mask", json={"text": text}).json()


def test_model_json_is_retried_once_when_format_is_wrong(monkeypatch):
    answers = iter(["후보는 없습니다.", '{"candidates":[{"scheme_id":"S-002","reason":"체납","evidence":"전기요금 체납"}]}'])
    calls = []

    async def model(*_args, **_kwargs):
        calls.append(1)
        return next(answers)

    monkeypatch.setattr(agents, "_run_agent", model)
    data = masked_flow()
    result = client.post("/api/match", json={"masked_text": data["masked_text"], "mask_token": data["mask_token"]}).json()
    assert len(calls) == 2
    assert result["is_fallback"] is False and [c["scheme_id"] for c in result["candidates"]] == ["S-002"]


def test_model_json_falls_back_after_second_bad_format(monkeypatch):
    calls = []

    async def model(*_args, **_kwargs):
        calls.append(1)
        return "형식 없음"

    monkeypatch.setattr(agents, "_run_agent", model)
    data = masked_flow()
    result = client.post("/api/match", json={"masked_text": data["masked_text"], "mask_token": data["mask_token"]}).json()
    assert len(calls) == 2 and result["is_fallback"] is True


def test_rate_limit_blocks_excess_model_calls(monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 3)
    data = masked_flow()
    body = {"masked_text": data["masked_text"], "mask_token": data["mask_token"]}
    statuses = [client.post("/api/match", json=body).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


def test_additional_personal_data_kinds_are_masked():
    result = mask_personal_data("연락은 hong@example.com, 계좌 110-123-456789, 생년월일 1946.03.05 입니다.")
    assert "hong@example.com" not in result.masked_text
    assert "110-123-456789" not in result.masked_text
    assert "1946.03.05" not in result.masked_text
    assert result.counts == {"email": 1, "account": 1, "date": 1}


def test_unmasked_sensitive_terms_trigger_a_warning():
    result = mask_personal_data("어르신이 무릎 수술을 받았고 소득이 거의 없습니다.")
    assert any("가려지지 않고" in warning for warning in result.warnings)
    assert not mask_personal_data("이웃이 안부를 물었습니다.").warnings
