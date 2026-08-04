"""이미 만들어진 초안에 독자 반응을 뒤늦게 붙입니다.

독자 검수 기능이 생기기 전에 만들어진 초안이나, 독자 명단을 바꾼 뒤
다시 받아보고 싶을 때 씁니다. 아무것도 발행하지 않습니다.

  .venv\\Scripts\\python.exe tools\\review_existing.py           # 아직 안 받은 것 전부
  .venv\\Scripts\\python.exe tools\\review_existing.py 20260802-1 # 특정 초안만
  .venv\\Scripts\\python.exe tools\\review_existing.py --all      # 이미 받은 것도 다시
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import reviewers  # noqa: E402
from src.settings import load_config  # noqa: E402

POSTS = ROOT / "posts"


def targets(args: list[str]) -> list[Path]:
    redo = "--all" in args
    picked = [a for a in args if not a.startswith("--")]
    out = []
    for folder in sorted(POSTS.glob("2*")):
        path = folder / "post.json"
        if not path.exists():
            continue
        if picked and folder.name not in picked:
            continue
        post = json.loads(path.read_text(encoding="utf-8"))
        if post.get("published"):
            continue  # 이미 올린 글은 검수해도 소용없습니다
        if post.get("reviews") and not redo and not picked:
            continue
        out.append(path)
    return out


def main() -> int:
    args = sys.argv[1:]
    paths = targets(args)
    if not paths:
        print("검수할 초안이 없습니다.")
        return 0

    config = load_config()
    print(f"{len(paths)}건을 검수합니다.\n")

    for path in paths:
        post = json.loads(path.read_text(encoding="utf-8"))
        book = {
            "title": post["title"],
            "author_display": post.get("author", ""),
        }
        copy = {"slides": post.get("slides", []), "search_line": post.get("search_line", "")}

        print("=" * 60)
        print(f"{post['slug']}  {post['title']}")
        print(f"  원문 소개글 {post.get('source_len', '?')}자")
        print("-" * 60)

        out = reviewers.review(book, copy, config)
        if not out:
            print("  검수 실패 — 건너뜁니다\n")
            continue

        for r in out:
            mark = "○ 멈춤" if r["행동"] == "멈춰서 읽음" else "× 넘김"
            tags = " ".join(t for t, on in (("저장", r["저장"]), ("팔로우", r["팔로우"])) if on)
            print(f"  {mark}  {r['이름']}({r['나이']}) {tags}")
            print(f"     \"{r['한마디']}\"")
            if r["걸린점"]:
                print(f"     걸린점: {r['걸린점']}")

        summary = reviewers.summarize(out)
        post["reviews"] = out
        post["review_summary"] = summary
        path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")

        print("-" * 60)
        print(
            f"  멈춤 {summary['멈춤']}/{summary['인원']} · "
            f"저장 {summary['저장']} · 팔로우 {summary['팔로우']}"
        )
        print(f"  → {summary['진단']}\n")

    print("post.json 에 저장했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
