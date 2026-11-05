"""결정론적 개인정보 마스킹. 모델을 호출하지 않으며 원문을 저장하거나 기록하지 않는다."""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

SURNAMES = set(
    "김이박최정강조윤장임한오서신권황안송류홍전고문양손배백허유남심노하곽성차주우구민나진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용봉"
)
HONORIFICS = "어르신|씨|님|할머니|할아버지|환자|대상자|어머니|아버지"
NOT_NAMES = {
    "이웃", "주민", "독거", "고령", "노인", "일반", "해당", "담당", "보호", "가족", "남성", "여성",
    "최근", "전화", "주소", "도움", "마을", "한국", "정신", "주변", "신청", "대상", "성명", "이름",
    "보호자", "신청인", "대상자", "방문", "상담", "연락", "사례", "소득", "가구",
}

RRN_RE = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")
MOBILE_RE = re.compile(r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)0(?:2|[3-6]\d)[-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")
ADDRESS_RE = re.compile(
    r"(?:[가-힣]{1,6}(?:특별시|광역시|특별자치시|특별자치도|시|군|구|읍|면|동|리|로|길)\s*){1,6}"
    r"\d{1,5}(?:-\d{1,4})?(?:번지|호)?"
)
NAME_BY_HONORIFIC_RE = re.compile(rf"(?<![가-힣])([가-힣]{{2,4}})(?=\s*(?:{HONORIFICS})(?![가-힣]))")
NAME_BY_LABEL_RE = re.compile(r"(?:성명|이름|보호자|대상자|신청인)\s*[:：]?\s*([가-힣]{2,4})(?![가-힣])")

LABELS = {"phone": "전화", "rrn": "주민번호", "address": "주소", "name": "이름"}
KIND_ORDER = ["name", "phone", "rrn", "address"]


@dataclass
class MaskResult:
    masked_text: str
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class _Placeholders:
    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], str] = {}
        self._counter: dict[str, int] = {}

    def get(self, kind: str, value: str) -> str:
        key = (kind, re.sub(r"\s+", "", value))
        if key not in self._seen:
            index = self._counter.get(kind, 0)
            self._counter[kind] = index + 1
            letter = string.ascii_uppercase[index % 26] * (index // 26 + 1)
            self._seen[key] = f"[{LABELS[kind]}{letter}]"
        return self._seen[key]

    def distinct_counts(self) -> dict[str, int]:
        return {kind: count for kind, count in self._counter.items() if count}


def _find_names(text: str) -> list[str]:
    candidates: list[str] = []
    for match in NAME_BY_HONORIFIC_RE.finditer(text):
        name = match.group(1)
        if name[0] in SURNAMES and name not in NOT_NAMES:
            candidates.append(name)
    for match in NAME_BY_LABEL_RE.finditer(text):
        name = match.group(1)
        if name not in NOT_NAMES:
            candidates.append(name)
    return sorted(set(candidates), key=len, reverse=True)


def mask_personal_data(text: str) -> MaskResult:
    placeholders = _Placeholders()
    names = _find_names(text)
    masked = text

    for pattern, kind in (
        (RRN_RE, "rrn"),
        (MOBILE_RE, "phone"),
        (LANDLINE_RE, "phone"),
        (ADDRESS_RE, "address"),
    ):
        masked = pattern.sub(lambda m, k=kind: placeholders.get(k, m.group(0)), masked)

    for name in names:
        masked = masked.replace(name, placeholders.get("name", name))

    counts = placeholders.distinct_counts()
    warnings: list[str] = []
    if counts.get("rrn"):
        warnings.append("주민등록번호 형태가 발견되어 가렸습니다. 실제 개인정보는 입력하지 마세요.")
    return MaskResult(masked_text=masked, counts=counts, warnings=warnings)
