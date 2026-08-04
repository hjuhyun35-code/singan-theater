"""알라딘 Open API에서 신간/베스트셀러를 가져옵니다.

알라딘 JSON 응답은 본문에 줄바꿈이 그대로 들어가 깨지는 경우가 잦아,
안정적인 XML 응답을 파싱합니다.
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime

import requests

from .settings import env

LIST_URL = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
LOOKUP_URL = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
VERSION = "20131101"
TIMEOUT = 20
RETRIES = 5

# 알라딘이 기본 python-requests 요청을 막는 경우가 있어 브라우저처럼 보내고,
# 어디서 쓰는지도 밝힙니다.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml,text/xml,*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.aladin.co.kr/",
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = _WS.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _item_to_dict(item: ET.Element) -> dict:
    """<item> 엘리먼트를 평평한 사전으로 바꿉니다. subInfo 안쪽까지 훑습니다."""
    data: dict[str, str] = {}
    for child in item.iter():
        if child is item:
            continue
        name = _localname(child.tag)
        if child.text and child.text.strip() and name not in data:
            data[name] = child.text.strip()
    return data


def _request(url: str, params: dict) -> list[dict]:
    params = {**params, "ttbkey": env("ALADIN_TTB_KEY", required=True), "Version": VERSION, "output": "xml"}
    last = ""
    for attempt in range(RETRIES):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 403:
                # 해외 서버에서 간헐적으로 막힙니다. 간격을 늘려가며 다시 시도합니다.
                last = "403 (알라딘이 이 서버의 접근을 거부)"
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            body = resp.text
            if "잘못된" in body and "<item" not in body:
                raise RuntimeError(f"알라딘 API 오류 응답: {_clean(body)[:200]}")
            root = ET.fromstring(body.encode("utf-8"))
            return [_item_to_dict(el) for el in root.iter() if _localname(el.tag) == "item"]
        except (requests.RequestException, ET.ParseError) as exc:
            last = str(exc)
            if attempt == RETRIES - 1:
                break
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"알라딘 API 호출 실패: {last}")


def fetch_list(query_type: str, category_id: int, max_results: int = 10) -> list[dict]:
    """신간/베스트셀러 목록을 가져옵니다."""
    return _request(
        LIST_URL,
        {
            "QueryType": query_type,
            "CategoryId": category_id,
            "MaxResults": min(max_results, 50),
            "start": 1,
            "SearchTarget": "Book",
            "Cover": "Big",
            # 평점·판매지수를 목록에서 같이 받아, 후보를 고를 때 상세 조회를
            # 열 번씩 하지 않아도 되게 합니다.
            "OptResult": "ratingInfo,itemPage",
        },
    )


def fetch_detail(isbn13: str) -> dict:
    """책 한 권의 상세 정보(소개글 전문, 목차)를 가져옵니다."""
    items = _request(
        LOOKUP_URL,
        {
            "ItemId": isbn13,
            "ItemIdType": "ISBN13",
            "Cover": "Big",
            "OptResult": "Toc,Story,fullDescription,authors,ratingInfo,bestSellerRank",
        },
    )
    return items[0] if items else {}


_ROLE = re.compile(r"\((지은이|옮긴이|엮은이|감수|그림|글|사진|편저|원작)[^)]*\)")


def primary_author(raw: str) -> str:
    """'모건 하우절 (지은이), 이지연 (옮긴이)' -> '모건 하우절'

    카드에 넣을 짧은 저자 표기를 만듭니다. 옮긴이는 떼고 지은이만 남깁니다.
    """
    if not raw:
        return ""
    writers = [
        _ROLE.sub("", part).strip()
        for part in raw.split(",")
        if "옮긴이" not in part and "감수" not in part
    ]
    writers = [w for w in writers if w]
    if not writers:
        writers = [_ROLE.sub("", raw.split(",")[0]).strip()]
    if len(writers) > 2:
        return f"{writers[0]} 외 {len(writers) - 1}명"
    return " · ".join(writers)


def _parse_date(raw: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


# 알라딘은 같은 책의 판형·굿즈 상품을 제목 뒤 괄호로 구분합니다.
# 이건 책 이름이 아니라 상품 이름이라 카드에 그대로 나오면 지저분합니다.
# '(알라딘 리커버 특별판)', '(집 에디션)' 처럼 앞에 수식어가 붙기도 합니다.
# 다만 괄호 안이 길면 부제일 수 있어, 짧은 괄호만 판형 표기로 봅니다.
_EDITION = re.compile(
    r"\s*[(\[]\s*[^)\]]{0,8}?(?:사인|친필|특별|한정|리커버|개정|양장|무선|스페셜|증보|"
    r"합본|세트|보급|미니|박스|에디션|초판|기념|반양장)[^)\]]{0,8}[)\]]\s*$"
)


def _strip_edition(title: str) -> str:
    """'태양 아래 올리브 (사인인쇄본)' → '태양 아래 올리브'.

    여러 개가 겹쳐 붙는 경우가 있어 더 지울 게 없을 때까지 반복합니다.
    다 지우면 빈 문자열이 되니, 그때는 원래 제목을 그대로 둡니다.
    """
    out = title.strip()
    while True:
        trimmed = _EDITION.sub("", out).strip()
        if trimmed == out:
            break
        out = trimmed
    return out or title.strip()


def _int(value) -> int:
    """알라딘은 빈 칸을 '' 로도 보내고 아예 안 보내기도 합니다."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _float(value) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def normalize(raw: dict, detail: dict | None = None) -> dict:
    """알라딘 응답을 우리가 쓰기 좋은 형태로 정리합니다."""
    d = {**raw, **(detail or {})}
    description = _clean(d.get("fullDescription") or d.get("description"))
    toc = _clean(d.get("toc"))
    cover = d.get("cover", "")
    # 알라딘 표지 URL의 크기 코드를 큰 이미지로 올립니다.
    # 다만 책에 따라 cover500 이 없을 수 있어, 원본 주소도 함께 남겨둡니다.
    cover_large = re.sub(r"/cover(sum|\d*)?/", "/cover500/", cover)
    return {
        "isbn13": (d.get("isbn13") or d.get("isbn") or "").strip(),
        "title": _strip_edition(_clean(d.get("title"))),
        # 알라딘 제목에는 부제가 ' - ' 뒤에 붙어 있습니다.
        # 카드와 검색줄에는 짧은 제목만 씁니다.
        "short_title": _strip_edition(_clean(d.get("title")).split(" - ")[0]),
        "subtitle": _clean(d.get("subTitle")),
        "author": _clean(d.get("author")),
        "author_display": primary_author(_clean(d.get("author"))),
        "publisher": _clean(d.get("publisher")),
        "pub_date": (d.get("pubDate") or "").strip(),
        "pub_date_obj": _parse_date(d.get("pubDate", "")),
        "cover_url": cover_large,
        "cover_url_fallback": cover,
        "link": d.get("link", ""),
        "category": _clean(d.get("categoryName")),
        "description": description,
        "toc": toc[:3000],
        "page_count": _int(d.get("itemPage")),
        # 얼마나 읽힌 책인지. 소개글이 짧아도 이건 사실이라 그대로 쓸 수 있습니다.
        # rank(0~10)와 salesPoint 는 목록 응답에도 들어 있어 후보를 고를 때 씁니다.
        # review_count 는 상세 조회(ratingInfo)에서만 옵니다.
        "rating_rank": _int(d.get("customerReviewRank")),
        "rating_score": _float(d.get("ratingScore")),
        "rating_count": _int(d.get("ratingCount")),
        "review_count": _int(d.get("myReviewCount")),
        "sales_point": _int(d.get("salesPoint")),
    }


def affiliate_link(link: str, partner_id: str) -> str:
    if not partner_id or not link:
        return link
    joiner = "&" if "?" in link else "?"
    return f"{link}{joiner}ttbkey={partner_id}"
