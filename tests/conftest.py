import pytest

from app import agents


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch):
    """시험에서는 실제 모델을 호출하지 않는다(토큰이 있어도)."""
    from app import main

    main._recent_calls.clear()

    async def fail(*_args, **_kwargs):
        raise RuntimeError("model unavailable in tests")

    async def fail_stream(*_args, **_kwargs):
        raise RuntimeError("model unavailable in tests")
        yield ""

    monkeypatch.setattr(agents, "_run_agent", fail)
    monkeypatch.setattr(agents, "_stream_agent", fail_stream)
    monkeypatch.setattr(agents, "FALLBACK_DELAY_SECONDS", 0)
