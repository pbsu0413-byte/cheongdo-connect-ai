import json

from fastapi.testclient import TestClient

from app import agents
from app.main import app

client = TestClient(app)


def masked_flow(text="홍길순 어르신 연락처 010-0000-0001. 혼자 거주하며 전기요금 3개월 체납."):
    return client.post("/api/mask", json={"text": text}).json()


def parse_sse(body: str):
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return events


def test_draft_stream_requires_confirmation_token():
    response = client.post("/api/draft/stream", json={"masked_text": "x", "mask_token": "", "scheme_id": "S-002"})
    assert response.status_code == 403


def test_draft_stream_falls_back_and_marks_it(monkeypatch):
    monkeypatch.setattr(agents, "FALLBACK_DELAY_SECONDS", 0)
    data = masked_flow()
    response = client.post(
        "/api/draft/stream",
        json={"masked_text": data["masked_text"], "mask_token": data["mask_token"], "scheme_id": "S-002"},
    )
    events = parse_sse(response.text)
    assert events[0][0] == "status"
    done = events[-1]
    assert done[0] == "done"
    assert done[1]["is_fallback"] is True and done[1]["ai_generated"] is False
    assert done[1]["draft_token"] and done[1]["elapsed_ms"] >= 0


def test_draft_stream_forwards_model_chunks(monkeypatch):
    async def fake_stream(*_args, **_kwargs):
        for chunk in ("신청", " 초안"):
            yield chunk

    monkeypatch.setattr(agents, "_stream_agent", fake_stream)
    data = masked_flow()
    response = client.post(
        "/api/draft/stream",
        json={"masked_text": data["masked_text"], "mask_token": data["mask_token"], "scheme_id": "S-002"},
    )
    events = parse_sse(response.text)
    assert [e[1]["text"] for e in events if e[0] == "delta"] == ["신청", " 초안"]
    assert events[-1][1]["draft"] == "신청 초안" and events[-1][1]["is_fallback"] is False


def test_review_requires_confirmation_token():
    response = client.post(
        "/api/review", json={"masked_text": "x", "mask_token": "", "scheme_id": "S-002", "draft_text": "초안"}
    )
    assert response.status_code == 403


def test_review_fallback_flags_eligibility_claims():
    data = masked_flow()
    response = client.post(
        "/api/review",
        json={
            "masked_text": data["masked_text"],
            "mask_token": data["mask_token"],
            "scheme_id": "S-002",
            "draft_text": "신청인은 지원을 받을 수 있습니다.",
        },
    ).json()
    assert response["is_fallback"] is True and response["ai_generated"] is False
    assert any("받을 수 있습니다" in issue["quote"] for issue in response["issues"])


def test_review_uses_model_issues(monkeypatch):
    async def model(*_args, **_kwargs):
        return '{"issues":[{"text":"메모에 없는 금액이 있습니다.","quote":"50만 원"}]}'

    monkeypatch.setattr(agents, "_run_agent", model)
    data = masked_flow()
    response = client.post(
        "/api/review",
        json={
            "masked_text": data["masked_text"],
            "mask_token": data["mask_token"],
            "scheme_id": "S-002",
            "draft_text": "지원금 50만 원 [확인 필요: 금액]",
        },
    ).json()
    assert response["is_fallback"] is False
    assert response["issues"] == [{"text": "메모에 없는 금액이 있습니다.", "quote": "50만 원"}]
