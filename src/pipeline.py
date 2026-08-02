"""신간을 골라 → 문구를 쓰고 → 카드를 만들어 → 초안으로 저장합니다.

여기까지는 아무것도 발행하지 않습니다. 발행은 승인 화면에서 직접 누를 때만 일어납니다.
"""

from datetime import date

from . import aladin, card, store, writer
from .settings import ensure_dirs, load_config

MIN_DESCRIPTION = 80  # 소개글이 이보다 짧으면 쓸 말이 없습니다


def _pick_candidates(config: dict) -> list[dict]:
    """설정한 분야들에서 후보 책을 모읍니다. 분야를 번갈아 담아 한쪽으로 쏠리지 않게 합니다."""
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


def _within_window(book: dict, config: dict) -> bool:
    pub = book.get("pub_date_obj")
    if pub is None:
        return True
    age = (date.today() - pub).days
    return (
        int(config["수집"]["최소_출간후_경과일"])
        <= age
        <= int(config["수집"]["최대_출간후_경과일"])
    )


def generate(limit: int | None = None) -> list[int]:
    """초안을 만들고, 만들어진 초안 ID 목록을 돌려줍니다."""
    ensure_dirs()
    config = load_config()
    target = limit or int(config["수집"]["하루_초안수"])

    print("신간 목록을 가져오는 중...")
    candidates = _pick_candidates(config)
    print(f"후보 {len(candidates)}권 확보. 여기서 {target}권을 고릅니다.\n")

    created: list[int] = []
    for book in candidates:
        if len(created) >= target:
            break
        if store.already_seen(book["isbn13"]):
            continue
        if not _within_window(book, config):
            continue

        try:
            detail = aladin.fetch_detail(book["isbn13"])
        except RuntimeError as exc:
            print(f"  ! 상세정보 실패 [{book['title']}]: {exc}")
            continue

        if detail:
            # 상세 응답에는 목록보다 훨씬 긴 소개글과 목차가 들어 있습니다.
            book = aladin.normalize(detail)
        if len(book["description"]) < MIN_DESCRIPTION:
            print(f"  - 건너뜀 [{book['title']}]: 소개글이 너무 짧아 쓸 내용이 없습니다")
            store.mark_seen(book["isbn13"], book["title"])
            continue

        print(f"  · 작성 중: {book['title']}")
        try:
            copy = writer.write_copy(book, config)
        except Exception as exc:  # 모델 호출 실패는 다음 책으로 넘어갑니다
            print(f"  ! 문구 생성 실패 [{book['title']}]: {exc}")
            continue

        if copy.get("confidence") == "low":
            print("    (자료가 빈약해 내용이 얕을 수 있습니다 — 승인 화면에서 확인하세요)")
        if copy.get("copy_overlap", 0) >= writer.COPY_OVERLAP_LIMIT:
            print(f"    (주의: 소개글과 {copy['copy_overlap']}자 겹칩니다 — 직접 고쳐 쓰세요)")

        cards = card.render_cards(
            book,
            copy,
            config["발행"].get("표지_사용", True),
            config["제휴"].get("출처표기_문구", "")
            if config["제휴"].get("출처표기_사용")
            else "",
        )
        draft_id = store.save_draft(book, copy, cards)
        store.mark_seen(book["isbn13"], book["title"])
        created.append(draft_id)
        print(f"    → 초안 #{draft_id} 저장, 카드 {len(cards)}장\n")

    return created
