"""가상 제도 데이터와 샘플 메모 로더(읽기 전용)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_schemes() -> dict[str, Any]:
    return json.loads((DATA_DIR / "care_schemes.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_samples() -> dict[str, Any]:
    return json.loads((DATA_DIR / "sample_memos.json").read_text(encoding="utf-8"))


def scheme_by_id() -> dict[str, dict[str, Any]]:
    return {scheme["id"]: scheme for scheme in load_schemes()["schemes"]}
