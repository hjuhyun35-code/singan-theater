"""인스타에 올릴 정사각/세로형 카드 이미지를 만듭니다.

HTML을 크롬으로 열어 사진처럼 찍는 방식이라, 디자인을 바꾸고 싶으면
templates/card.html 의 CSS만 고치면 됩니다.
인스타 API는 JPEG만 받으므로 JPEG로 저장합니다.
"""

import base64
import re

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from . import palette
from .settings import CARD_DIR, ROOT

WIDTH, HEIGHT = 1080, 1350
JPEG_QUALITY = 92

_env = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html"]),
)


def _safe_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_")[:40] or "book"


# 포스터 제목에 쓰는 굵은 한글 글꼴. 저장소에 같이 두어야 CI에서도 똑같이 나옵니다.
# 검은고딕 (SIL Open Font License 1.1) — 상업적 사용·임베딩 모두 허용.
DISPLAY_FONT = ROOT / "assets" / "fonts" / "BlackHanSans-Regular.ttf"
_font_cache: str | None = None


def display_font_uri() -> str:
    """글꼴 파일을 data 주소로 만듭니다.

    set_content 로 HTML을 넣으면 기준 주소가 없어서 상대 경로 글꼴을 못 찾습니다.
    그래서 파일을 통째로 HTML 안에 심습니다. 파일이 없으면 빈 문자열을 주고,
    템플릿은 기본 글꼴로 조용히 되돌아갑니다.
    """
    global _font_cache
    if _font_cache is None:
        try:
            b64 = base64.b64encode(DISPLAY_FONT.read_bytes()).decode()
            _font_cache = f"data:font/ttf;base64,{b64}"
        except OSError:
            _font_cache = ""
    return _font_cache


def _fetch_one(url: str) -> tuple[str, bytes]:
    resp = requests.get(
        url,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.aladin.co.kr/"},
    )
    resp.raise_for_status()
    mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if not mime.startswith("image/"):
        return "", b""  # 표지가 지워진 경우 알라딘이 오류 페이지를 돌려줍니다
    return (
        f"data:{mime};base64,{base64.b64encode(resp.content).decode('ascii')}",
        resp.content,
    )


def _cover_data_uri(*urls: str) -> str:
    """표지 이미지를 내려받아 HTML 안에 직접 심습니다.

    고화질 주소부터 시도하고, 그 크기가 없는 책이면 원본 주소로 되돌아갑니다.
    (URL을 그대로 쓰지 않고 직접 받는 이유는 알라딘이 외부 참조를 막을 수 있어서입니다.)
    """
    return _cover_with_bytes(*urls)[0]


def _cover_with_bytes(*urls: str) -> tuple[str, bytes]:
    """카드에 심을 데이터 주소와, 색을 뽑을 원본 바이트를 함께 돌려줍니다."""
    tried: set[str] = set()
    for url in urls:
        if not url or url in tried:
            continue
        tried.add(url)
        try:
            data, raw = _fetch_one(url)
            if data:
                return data, raw
        except requests.RequestException:
            continue
    return "", b""


_EMPH = re.compile(r"\*([^*]+)\*")


def _plain(text: str) -> str:
    """강조 표시(*)를 걷어낸 순수 문자열. 글자 수를 셀 때 씁니다."""
    return _EMPH.sub(r"\1", text).strip()


# 앞말에 붙어서만 뜻이 사는 낱말들. 줄 첫머리에 혼자 떨어지면 읽기 나쁩니다.
# '맞부딪칠 / 때 무엇이 남는가' 처럼 끊긴 카드가 실제로 나왔습니다.
_CLING = (
    "때", "것", "수", "줄", "리", "뿐", "채", "만큼", "데", "바", "듯",
    "대로", "뒤", "앞", "후", "중", "적", "번", "말", "터",
)
_CLING_RE = re.compile(
    r"(?<=\S) (?=(?:" + "|".join(_CLING) + r")(?:[은는이가을를의도만에과와로]|였|이었)?[.,?! ]?(?:\s|$))"
)


def _glue(text: str) -> str:
    """의존명사 앞의 띄어쓰기를 '안 끊기는 빈칸'으로 바꿉니다.

    CSS 는 한국어 구(句)를 모르기 때문에 어절 단위로만 끊습니다.
    보이는 모양은 그대로고, 줄바꿈만 그 자리에서 일어나지 않습니다.
    """
    return _CLING_RE.sub(" ", text)


def _split_emphasis(text: str) -> list[dict]:
    """'앞말 *강조* 뒷말' 을 조각으로 나눕니다. 템플릿이 색을 입힙니다."""
    parts: list[dict] = []
    last = 0
    for m in _EMPH.finditer(text):
        if m.start() > last:
            parts.append({"t": text[last : m.start()], "em": False})
        parts.append({"t": m.group(1), "em": True})
        last = m.end()
    if last < len(text):
        parts.append({"t": text[last:], "em": False})
    return [p for p in parts if p["t"]]


def build_slides(book: dict, copy: dict, credit: str = "") -> list[dict]:
    """생성된 문구를 카드 장별 데이터로 배치합니다."""
    slides = copy.get("slides") or []
    total = len(slides)
    rendered = []
    for i, slide in enumerate(slides, start=1):
        kind = slide.get("type", "")
        prev_kind = slides[i - 2].get("type", "") if i > 1 else ""
        headline = slide.get("headline", "") or ""
        rendered.append(
            {
                "kind": kind,
                "kicker": slide.get("kicker", ""),
                "headline": _plain(headline),
                # *별표* 로 감싼 부분은 강조색으로 칠합니다.
                "headline_parts": _split_emphasis(_glue(headline)),
                "body": slide.get("body", ""),
                # 줄바꿈으로 나눈 각 문장. 길어서 자동으로 넘어간 줄과
                # 일부러 끊은 줄이 헷갈리지 않도록 문단으로 나눠 그립니다.
                "body_lines": [
                    _glue(line.strip())
                    for line in (slide.get("body") or "").split("\n")
                    if line.strip()
                ],
                "index": i,
                "total": total,
                # 앞장에서 이어지는 장면인지. 같은 종류가 연달아 나오면 이어짐입니다.
                "continues": kind != "" and kind == prev_kind,
                "show_cover": i == 1,
                # 마무리 스타일은 맨 끝 장에만. (중간에 놓인 '정리'까지 가운데정렬되면 어색합니다)
                "is_outro": i == total and total > 1,
                # 카드에는 부제를 뺀 짧은 제목을 씁니다. 안 그러면 하단 표기가 넘칩니다.
                "title": book.get("short_title") or book["title"],
                "author": book.get("author_display") or book.get("author", ""),
                "publisher": book["publisher"],
                # 출처 표기는 마지막 장에만. 알라딘 상위 등급 심사 때 근거가 됩니다.
                "credit": credit if i == total else "",
            }
        )
    return rendered


def render_cards(
    book: dict,
    copy: dict,
    use_cover: bool = True,
    credit: str = "",
    theme: str = "밤",
    accent_from_cover: bool = True,
    back_cover: str = "없음",
    style: str = "기본",
    # 글자에 가로 줄무늬(긁힌 인쇄)를 입힐지. 기본은 꺼짐 — 읽기 나쁘고 지저분합니다.
    # 공포·스릴러처럼 일부러 낡은 느낌을 낼 때만 켜세요. (포스터 스타일에서만 먹습니다)
    scratch: bool = False,
) -> list[str]:
    """카드 이미지를 만들고 저장된 파일 경로 목록을 돌려줍니다.

    use_cover 가 False 면 표지를 넣지 않고 글자만으로 첫 장을 만듭니다.
    (책 표지는 출판사 저작권 자산이라 선택할 수 있게 뒀습니다.)
    """
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    slides = build_slides(book, copy, credit)
    if not slides:
        return []

    # 표지는 카드에 심을 용도와, 강조색을 뽑을 용도로 둘 다 씁니다.
    cover, raw = _cover_with_bytes(
        book.get("cover_url", ""), book.get("cover_url_fallback", "")
    )
    accent = palette.accent_from_cover(raw, theme) if (raw and accent_from_cover) else None
    if not use_cover:
        cover = ""  # 표지는 안 넣더라도 색은 가져다 씁니다
    template = _env.get_template("card.html")
    prefix = f"{book['isbn13']}_{_safe_name(book['title'])}"
    paths: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        try:
            for slide in slides:
                html = template.render(
                    cover_url=cover,
                    theme=theme,
                    accent=accent,
                    back_cover=back_cover,
                    style=style,
                    scratch=scratch,
                    display_font=display_font_uri(),
                    **slide,
                )
                page.set_content(html, wait_until="load")
                page.wait_for_timeout(120)  # 폰트가 자리를 잡을 시간
                out = CARD_DIR / f"{prefix}_{slide['index']}.jpg"
                page.screenshot(path=str(out), type="jpeg", quality=JPEG_QUALITY)
                paths.append(str(out))
        finally:
            browser.close()
    return paths
