"""GitHub Actions에서 초안을 만듭니다.

만들어진 결과는 posts/<슬러그>/ 폴더에 들어갑니다.
  card1.jpg ... cardN.jpg   인스타에 올릴 카드
  post.json                 캡션, 대체텍스트, 쓰레드 본문

여기서는 아무것도 발행하지 않습니다. 발행은 publish 워크플로에서 따로 합니다.
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import aladin, card, nlk, reviewers, writer  # noqa: E402
from src.aladin import affiliate_link  # noqa: E402
from src.settings import load_config  # noqa: E402

POSTS = ROOT / "posts"
SEEN_PATH = POSTS / "seen.json"
MIN_DESCRIPTION = 80


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    POSTS.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def next_slug() -> str:
    """오늘 날짜 + 순번. 발행할 때 손으로 입력해야 해서 짧게 만듭니다."""
    today = date.today().strftime("%Y%m%d")
    used = {p.name for p in POSTS.glob(f"{today}-*")} if POSTS.exists() else set()
    for n in range(1, 100):
        slug = f"{today}-{n}"
        if slug not in used:
            return slug
    raise RuntimeError("오늘 슬러그가 99개를 넘었습니다.")


def pick_candidates(config: dict) -> list[dict]:
    per_source = int(config["수집"]["분야당_후보수"])
    buckets: list[list[dict]] = []
    for genre in config["분야"]["목록"]:
        found: dict[str, dict] = {}
        for query_type in config["수집"]["종류"]:
            try:
                items = aladin.fetch_list(query_type, genre["카테고리ID"], per_source)
            except RuntimeError as exc:
                print(f"  ! {genre['이름']} / {query_type} 수집 실패: {exc}")
                continue
            for raw in items:
                book = aladin.normalize(raw)
                if book["isbn13"]:
                    found.setdefault(book["isbn13"], book)
        buckets.append(list(found.values()))

    merged, seen = [], set()
    for i in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if i < len(bucket) and bucket[i]["isbn13"] not in seen:
                seen.add(bucket[i]["isbn13"])
                merged.append(bucket[i])
    return merged


def within_window(book: dict, config: dict) -> bool:
    pub = book.get("pub_date_obj")
    if pub is None:
        return True
    age = (date.today() - pub).days
    return (
        int(config["수집"]["최소_출간후_경과일"])
        <= age
        <= int(config["수집"]["최대_출간후_경과일"])
    )


def build_credit(book: dict, config: dict) -> str:
    """실제로 쓴 자료의 출처만 표기합니다. 안 쓴 곳을 적으면 거짓말이 됩니다."""
    if not config["제휴"].get("출처표기_사용"):
        return ""
    parts = [config["제휴"].get("출처표기_문구", "")]
    if book.get("nlk_used"):
        parts.append(config["제휴"].get("국중_출처표기_문구", ""))
    return " / ".join(p for p in parts if p)


def build_post(book: dict, copy: dict, slug: str, config: dict) -> dict:
    partner = config["제휴"]["알라딘_파트너ID"]
    credit = build_credit(book, config)
    link = affiliate_link(book.get("link", ""), partner)
    hashtags = " ".join(copy["hashtags"])

    caption = "\n\n".join(
        p for p in [copy["search_line"], copy["threads_text"], hashtags, link, credit] if p
    )
    threads_text = writer.compose_threads_text(
        copy["threads_text"], hashtags, link, credit
    )

    return {
        "slug": slug,
        "isbn13": book["isbn13"],
        "title": book["title"],
        "short_title": book.get("short_title", book["title"]),
        "author": book.get("author_display") or book.get("author", ""),
        "publisher": book["publisher"],
        "pub_date": book["pub_date"],
        "link": link,
        "search_line": copy["search_line"],
        "caption": caption,
        "threads_text": threads_text,
        "hashtags": hashtags,
        "confidence": copy.get("confidence", ""),
        "copy_overlap": copy.get("copy_overlap", 0),
        # 재료가 얼마나 두꺼웠는지. 사실만 남기고 판정은 하지 않습니다.
        "source_len": len(book.get("description") or ""),
        "toc_len": len(book.get("toc") or ""),
        "reviews": [],
        "review_summary": {},
        # 카드에 들어간 문구를 그대로 남깁니다.
        # 나중에 디자인만 바꿔 다시 그릴 때 모델을 또 부르지 않아도 됩니다.
        "slides": copy["slides"],
        "cover_url": book.get("cover_url", ""),
        "cover_url_fallback": book.get("cover_url_fallback", ""),
        "cards": [],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "published": False,
    }


def main() -> int:
    config = load_config()
    limit = int(os.environ.get("DRAFT_COUNT") or config["수집"]["하루_초안수"])
    seen = load_seen()

    print("신간 목록을 가져오는 중...")
    candidates = pick_candidates(config)
    print(f"후보 {len(candidates)}권. 여기서 {limit}권을 고릅니다.\n")

    made: list[str] = []
    for book in candidates:
        if len(made) >= limit:
            break
        if book["isbn13"] in seen or not within_window(book, config):
            continue

        try:
            detail = aladin.fetch_detail(book["isbn13"])
        except RuntimeError as exc:
            print(f"  ! 상세정보 실패 [{book['title']}]: {exc}")
            continue
        if detail:
            book = aladin.normalize(detail)

        # 알라딘 기본 등급은 목차·전체 소개글을 안 줍니다. 국중에서 보강합니다.
        before = len(book["description"])
        book = nlk.enrich(book)
        if book.get("nlk_used"):
            print(
                f"    국중 보강: 소개글 {before}→{len(book['description'])}자"
                f"{', 목차 확보' if book.get('toc') else ''}"
            )

        if len(book["description"]) < MIN_DESCRIPTION:
            print(f"  - 건너뜀 [{book['title']}]: 소개글이 너무 짧습니다")
            seen[book["isbn13"]] = {"title": book["title"], "skipped": "소개글 부족"}
            continue

        # 출간 이력만 적힌 소개글이면 모델이 빈 곳을 상상으로 채웁니다. 미리 거릅니다.
        ok, why = writer.has_material(book, config)
        if not ok:
            print(f"  - 건너뜀 [{book['title']}]: 책 내용이 없는 소개글 ({why})")
            seen[book["isbn13"]] = {"title": book["title"], "skipped": f"재료 없음: {why}"}
            continue

        print(f"  · 작성 중: {book['title']}")
        try:
            copy = writer.write_copy(book, config)
        except Exception as exc:
            print(f"  ! 문구 생성 실패 [{book['title']}]: {exc}")
            continue

        slug = next_slug()
        out_dir = POSTS / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        # 카드 파일 이름은 반드시 영문. 한글 파일명은 이미지 주소에서 깨집니다.
        card.CARD_DIR = out_dir
        paths = card.render_cards(
            book,
            copy,
            config["발행"].get("표지_사용", True),
            build_credit(book, config),
            config["발행"].get("색테마", "밤"),
            config["발행"].get("표지색_강조", True),
            config["발행"].get("뒷장_표지", "없음"),
        )

        post = build_post(book, copy, slug, config)

        # 독자들이 넘겨보고 반응을 남깁니다. 발행을 막지는 않습니다.
        post["reviews"] = reviewers.review(book, copy, config)
        post["review_summary"] = reviewers.summarize(post["reviews"])
        if post["review_summary"]:
            s = post["review_summary"]
            print(
                f"    독자 {s['인원']}명 — 멈춤 {s['멈춤']} / 넘김 {s['넘김']} / "
                f"저장 {s['저장']} / 팔로우 {s['팔로우']}"
            )
        for i, (src_path, slide) in enumerate(zip(paths, copy["slides"]), start=1):
            dest = out_dir / f"card{i}.jpg"
            Path(src_path).replace(dest)
            post["cards"].append({"file": dest.name, "alt": slide.get("alt", "")})

        (out_dir / "post.json").write_text(
            json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        seen[book["isbn13"]] = {"title": book["title"], "slug": slug}
        made.append(slug)

        print(
            f"    → {slug} 카드 {len(post['cards'])}장 "
            f"(원문 {post['source_len']}자)\n"
        )

    save_seen(seen)

    # 다음 단계(텔레그램 알림)로 넘길 값
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"slugs={','.join(made)}\n")
            f.write(f"count={len(made)}\n")

    print(f"초안 {len(made)}건: {', '.join(made) if made else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
