import re
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VOID_TAGS = {"meta", "link", "br", "img", "input", "hr"}
MIN_TARGET_PX = 44


class ElementText(HTMLParser):
    """Collects the text inside every element that has an id."""

    def __init__(self):
        super().__init__()
        self.open_ids = []
        self.text = {}

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            element_id = dict(attrs).get("id")
            self.open_ids.append(element_id)
            if element_id:
                self.text.setdefault(element_id, "")

    def handle_endtag(self, tag):
        if tag not in VOID_TAGS and self.open_ids:
            self.open_ids.pop()

    def handle_data(self, data):
        for element_id in filter(None, self.open_ids):
            self.text[element_id] = self.text.get(element_id, "") + data


def page_text():
    parser = ElementText()
    parser.feed(client.get("/").text)
    return {key: " ".join(value.split()) for key, value in parser.text.items()}


def test_masking_confirmation_discloses_model_transfer():
    step2 = page_text()["step2"]
    assert "마스킹된 메모가 GitHub Copilot 모델로 전송됩니다. 서버는 원문과 모델 입출력을 저장하지 않습니다." in step2


def test_wait_notice_lives_in_the_progress_region_next_to_the_timer():
    text = page_text()
    assert "모델 응답에 약 20초가 걸릴 수 있습니다" in text["progress"]
    # app.js rewrites only this child, so the notice survives every timer tick.
    assert "progressText" in text


def test_not_checked_status_does_not_read_as_disconnected():
    js = client.get("/static/app.js").text
    labels = dict(re.findall(r"(\w+): \"([^\"]+)\"", js.split("MODEL_STATUS_LABELS = {")[1].split("};")[0]))
    assert labels["not_checked"] == "첫 요청 후 표시됩니다"


def declared_px(rules, selector_pattern):
    """Yields (selector, min-block-size in px) for rules whose last compound selector matches."""
    for selectors, body in rules:
        for selector in selectors.split(","):
            last = re.split(r"[\s>+~]+", selector.strip())[-1]
            if re.fullmatch(selector_pattern, last):
                match = re.search(r"(?:min-)?block-size:\s*([\d.]+)(px|rem)", body)
                if match:
                    yield selector.strip(), float(match[1]) * (16 if match[2] == "rem" else 1)


def stylesheet_rules():
    css = re.sub(r"/\*.*?\*/", "", client.get("/static/styles.css").text, flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def test_interactive_controls_are_at_least_44px_tall():
    rules = stylesheet_rules()
    sizes = dict(declared_px(rules, r"(button|select)(\.[\w-]+)*"))
    assert sizes["button"] >= MIN_TARGET_PX
    assert sizes["select"] >= MIN_TARGET_PX
    too_small = {selector: px for selector, px in sizes.items() if px < MIN_TARGET_PX}
    assert not too_small, too_small


def test_skip_link_is_at_least_44px_tall_when_focused():
    skip = dict(declared_px(stylesheet_rules(), r"\.skip"))
    assert skip.get(".skip", 0) >= MIN_TARGET_PX
