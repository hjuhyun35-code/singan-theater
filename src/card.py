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


def build_slides(book: dict, copy: dict, credit: str = "") -> list[dict]:
    """생성된 문구를 카드 장별 데이터로 배치합니다."""
    slides = copy.get("slides") or []
    total = len(slides)
    rendered = []
    for i, slide in enumerate(slides, start=1):
        kind = slide.get("type", "")
        prev_kind = slides[i - 2].get("type", "") if i > 1 else ""
        rendered.append(
            {
                "kind": kind,
                "kicker": slide.get("kicker", ""),
                "headline": slide.get("headline", ""),
                "body": slide.get("body", ""),
                # 줄바꿈으로 나눈 각 문장. 길어서 자동으로 넘어간 줄과
                # 일부러 끊은 줄이 헷갈리지 않도록 문단으로 나눠 그립니다.
                "body_lines": [
                    line.strip()
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
                    cover_url=cover, theme=theme, accent=accent, **slide
                )
                page.set_content(html, wait_until="load")
                page.wait_for_timeout(120)  # 폰트가 자리를 잡을 시간
                out = CARD_DIR / f"{prefix}_{slide['index']}.jpg"
                page.screenshot(path=str(out), type="jpeg", quality=JPEG_QUALITY)
                paths.append(str(out))
        finally:
            browser.close()
    return paths
