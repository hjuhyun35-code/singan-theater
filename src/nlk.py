"""국립중앙도서관 서지정보(seoji) API.

알라딘 기본 등급은 목차와 전체 소개글을 주지 않습니다.
여기서 그 두 가지를 받아와 재료를 두껍게 만듭니다.

주의: 목차·책소개는 출판사가 ISBN 등록 때 제출한 자료라 없는 책도 많습니다.
      수록률은 tools/nlk_coverage.py 로 실제로 재봐야 합니다.
"""

import re
import time

import requests

from .settings import env

SEARCH_URL = "https://www.nl.go.kr/seoji/SearchApi.do"
TIMEOUT = 20
RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 응답에서 쓸 항목: (우리 이름, 국중 필드명)
CONTENT_FIELDS = [
    ("toc", "BOOK_TB_CNT_URL"),          # 목차
    ("introduction", "BOOK_INTRODUCTION_URL"),  # 책소개
    ("summary", "BOOK_SUMMARY_URL"),     # 책요약
]

_TAG = re.compile(r"<[^>]+>")


def enabled() -> bool:
    return bool(env("NL_API_KEY"))


def _clean(text: str) -> str:
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _fetch_text(url: str) -> str:
    """목차·책소개는 본문이 아니라 '파일 주소'로 옵니다. 그 파일을 받아 글자만 남깁니다."""
    if not url or not url.startswith("http"):
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()
        if not any(t in ctype for t in ("text", "html", "xml", "json", "octet-stream")):
            return ""  # hwp/pdf 같은 건 건너뜁니다
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return _clean(resp.text)
    except requests.RequestException:
        return ""


def lookup(isbn13: str) -> dict:
    """ISBN 하나에 대한 목차·책소개·책요약. 없으면 빈 문자열로 채워 돌려줍니다."""
    blank = {name: "" for name, _ in CONTENT_FIELDS}
    key = env("NL_API_KEY")
    if not key or not isbn13:
        return blank

    params = {
        "cert_key": key,
        "result_style": "json",
        "page_no": 1,
        "page_size": 10,
        "isbn": isbn13,
    }
    doc = None
    for attempt in range(RETRIES):
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            docs = resp.json().get("docs") or []
            doc = docs[0] if docs else None
            break
        except (requests.RequestException, ValueError):
            if attempt == RETRIES - 1:
                return blank
            time.sleep(1.5 * (attempt + 1))

    if not doc:
        return blank

    out = dict(blank)
    for name, field in CONTENT_FIELDS:
        out[name] = _fetch_text((doc.get(field) or "").strip())
    return out


def enrich(book: dict) -> dict:
    """알라딘 책 정보에 국중 자료를 덧댑니다.

    소개글은 둘 중 '긴 쪽'을 씁니다. 알라딘 기본 등급은 100~200자뿐이라
    대개 국중 쪽이 두껍습니다.
    """
    if not enabled():
        return book

    extra = lookup(book.get("isbn13", ""))
    merged = dict(book)
    merged["nlk_used"] = False

    if extra["toc"] and not merged.get("toc"):
        merged["toc"] = extra["toc"][:3000]
        merged["nlk_used"] = True

    longer = max(
        (extra["introduction"], extra["summary"], merged.get("description", "")),
        key=len,
    )
    if longer and longer != merged.get("description", ""):
        merged["description"] = longer
        merged["nlk_used"] = True

    return merged
