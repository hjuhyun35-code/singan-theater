"""승인한 초안을 실제로 발행합니다.

카드 이미지는 이 저장소의 공개 주소(raw.githubusercontent.com)를 그대로 씁니다.
그래서 별도 이미지 호스팅 서비스가 필요 없습니다.

안전장치: confirm 값이 정확히 PUBLISH 가 아니면 직전까지만 해보고 멈춥니다.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import publisher  # noqa: E402

POSTS = ROOT / "posts"
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/posts/{slug}/{file}"


def card_urls(post: dict, repo: str, branch: str) -> list[str]:
    return [
        RAW.format(repo=repo, branch=branch, slug=post["slug"], file=c["file"])
        for c in post["cards"]
    ]


def check_reachable(urls: list[str]) -> None:
    """인스타가 가져갈 수 있는 주소인지 먼저 확인합니다.

    저장소가 비공개거나 커밋이 아직 반영되지 않았으면 여기서 걸립니다.
    """
    for url in urls:
        resp = requests.head(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(
                f"이미지를 열 수 없습니다 ({resp.status_code}): {url}\n"
                "  → 저장소가 공개(public)인지, 커밋이 푸시됐는지 확인하세요."
            )
        ctype = resp.headers.get("Content-Type", "")
        if "image" not in ctype:
            raise RuntimeError(f"이미지가 아닙니다 ({ctype}): {url}")
    print(f"  이미지 {len(urls)}장 접근 확인")


def main() -> int:
    slug = (os.environ.get("SLUG") or "").strip()
    confirm = (os.environ.get("CONFIRM") or "").strip()
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("BRANCH", "main")

    folder = POSTS / slug
    post_path = folder / "post.json"
    if not post_path.exists():
        print(f"[막힘] {slug} 초안을 찾을 수 없습니다.")
        print(f"       있는 것: {', '.join(sorted(p.name for p in POSTS.glob('2*'))) or '없음'}")
        return 1

    post = json.loads(post_path.read_text(encoding="utf-8"))
    if post.get("published"):
        print(f"[막힘] {slug} 는 이미 발행됐습니다. ({post.get('published_at')})")
        return 1

    urls = card_urls(post, repo, branch)
    print(f"발행 대상: {post['title']}")
    print(f"  카드 {len(urls)}장")
    print(f"  캡션 {len(post['caption'])}자 / 쓰레드 {len(post['threads_text'])}자")
    check_reachable(urls)

    if confirm != "PUBLISH":
        print("\n=== 예행연습입니다 (실제로 올리지 않았습니다) ===")
        print("실제로 올리려면 confirm 칸에 정확히 PUBLISH 를 입력하세요.\n")
        print(post["caption"])
        return 0

    alts = [c.get("alt", "") for c in post["cards"]]
    results = {}

    if os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        print("\n인스타그램에 올리는 중...")
        results["instagram"] = publisher.post_to_instagram(post["caption"], urls, alts)
        print(f"  완료: {results['instagram']}")

    if os.environ.get("THREADS_ACCESS_TOKEN"):
        print("쓰레드에 올리는 중...")
        results["threads"] = publisher.post_to_threads(post["threads_text"], urls)
        print(f"  완료: {results['threads']}")

    if not results:
        print("[막힘] 인스타·쓰레드 토큰이 하나도 없습니다.")
        return 1

    post["published"] = True
    post["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    post["post_ids"] = results
    post_path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n발행 완료: {', '.join(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
