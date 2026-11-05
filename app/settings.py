"""로컬 실행용 `.env` 로더. 이미 설정된 환경변수는 덮어쓰지 않는다(배포 환경은 앱 설정을 그대로 사용)."""

from __future__ import annotations

import os
from pathlib import Path


def load_env(path: Path | None = None) -> None:
    env_file = path or Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
