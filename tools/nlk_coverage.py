"""국립중앙도서관에 목차·책소개가 실제로 얼마나 들어 있는지 잽니다.

인증키를 받은 직후 이걸 먼저 돌리세요.
수록률이 낮으면 이 방향 자체를 접어야 하므로, 숫자를 먼저 봐야 합니다.

  .venv\\Scripts\\python.exe tools\\nlk_coverage.py        # 20권 표본
  .venv\\Scripts\\python.exe tools\\nlk_coverage.py 40     # 40권 표본
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import aladin, nlk  # noqa: E402
from src.settings import load_config  # noqa: E402


def main() -> int:
    if not nlk.enabled():
        print("NL_API_KEY 가 비어 있습니다. 인증키를 먼저 넣어주세요.")
        print("  .venv\\Scripts\\python.exe tools\\set_key.py 국중")
        return 1

    sample = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    config = load_config()

    books: dict[str, dict] = {}
    for genre in config["분야"]["목록"]:
        for query_type in config["수집"]["종류"]:
            try:
                for raw in aladin.fetch_list(query_type, genre["카테고리ID"], 20):
                    b = aladin.normalize(raw)
                    if b["isbn13"]:
                        books.setdefault(b["isbn13"], b)
            except RuntimeError as exc:
                print(f"  ! 수집 실패: {exc}")
    targets = list(books.values())[:sample]

    print(f"\n{len(targets)}권으로 수록률을 잽니다...\n")
    stats = {"toc": 0, "introduction": 0, "summary": 0, "found": 0}
    aladin_len, nlk_len = [], []

    for i, book in enumerate(targets, 1):
        got = nlk.lookup(book["isbn13"])
        marks = []
        if any(got.values()):
            stats["found"] += 1
        for name in ("toc", "introduction", "summary"):
            if got[name]:
                stats[name] += 1
                marks.append(f"{name} {len(got[name])}자")
        aladin_len.append(len(book["description"]))
        best = max(len(got["introduction"]), len(got["summary"]), len(book["description"]))
        nlk_len.append(best)
        print(f"{i:>3}. {book['short_title'][:24]:<26} {' / '.join(marks) or '없음'}")

    n = len(targets) or 1
    print("\n" + "=" * 52)
    print(f"  국중에서 뭐라도 찾은 책 : {stats['found']}/{n}  ({stats['found'] * 100 // n}%)")
    print(f"  목차 있음              : {stats['toc']}/{n}  ({stats['toc'] * 100 // n}%)  ← 가장 중요")
    print(f"  책소개 있음            : {stats['introduction']}/{n}  ({stats['introduction'] * 100 // n}%)")
    print(f"  책요약 있음            : {stats['summary']}/{n}  ({stats['summary'] * 100 // n}%)")
    print("-" * 52)
    print(f"  소개글 평균 길이  알라딘만: {sum(aladin_len) // n}자")
    print(f"                  국중 합산: {sum(nlk_len) // n}자")
    print("=" * 52)

    if stats["toc"] * 100 // n >= 40:
        print("\n쓸 만합니다. 목차가 이 정도면 '질문' 카드를 되살릴 수 있습니다.")
    else:
        print("\n목차 수록률이 낮습니다. 알라딘 상위 등급 신청 쪽이 더 확실해 보입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
