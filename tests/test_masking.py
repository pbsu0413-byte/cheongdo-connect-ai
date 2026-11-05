import json
from pathlib import Path

import pytest

from app.masking import mask_personal_data

SAMPLES = json.loads((Path(__file__).resolve().parent.parent / "data" / "sample_memos.json").read_text(encoding="utf-8"))["memos"]


def mask(sample_id: int):
    text = next(m["text"] for m in SAMPLES if m["id"] == sample_id)
    return text, mask_personal_data(text)


def test_phone_and_rrn_are_always_masked_in_all_samples():
    for sample in SAMPLES:
        result = mask_personal_data(sample["text"])
        assert "010-0000" not in result.masked_text
        assert "01000000002" not in result.masked_text
        assert "123456-2234567" not in result.masked_text


def test_sample_one_masks_every_kind_consistently():
    _, result = mask(1)
    assert "[이름A] 어르신" in result.masked_text
    assert "[전화A]" in result.masked_text
    assert "[주민번호A]" in result.masked_text
    assert "[주소A]" in result.masked_text
    assert result.counts == {"name": 1, "phone": 1, "rrn": 1, "address": 1}
    assert "홍길순" not in result.masked_text
    assert result.warnings


def test_same_name_gets_same_placeholder():
    _, result = mask(5)
    assert "최가상" not in result.masked_text
    assert result.masked_text.count("[이름A]") == 2


def test_two_phone_numbers_get_distinct_placeholders():
    _, result = mask(8)
    assert "[전화A]" in result.masked_text and "[전화B]" in result.masked_text
    assert "강가상" not in result.masked_text
    assert "이가족" not in result.masked_text


def test_road_and_lot_addresses_are_masked():
    _, road = mask(4)
    _, lot = mask(6)
    assert "가상로 12" not in road.masked_text
    assert "25번지" not in lot.masked_text


def test_memo_without_personal_data_is_not_over_masked():
    text, result = mask(9)
    assert result.masked_text == text
    assert result.counts == {}


def test_known_limit_english_name_is_not_detected():
    _, result = mask(7)
    assert "Gasang Kim" in result.masked_text
