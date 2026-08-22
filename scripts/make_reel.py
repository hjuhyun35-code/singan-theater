"""초안 하나로 릴스 영상을 만들어 텔레그램으로 보냅니다.

음악은 넣지 않습니다. 읽는 소리만 들어갑니다.
받으신 뒤 인스타 앱에서 음악을 붙여 올리시면 됩니다.
봇이 인스타에 직접 올리지는 않습니다 — 앱의 음악 목록을 API 로는 못 쓰기 때문입니다.

  python scripts/make_reel.py 20260806-1
  REEL_SLUG=20260806-1 python scripts/make_reel.py
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import reel  # noqa: E402

POSTS = ROOT / "posts"
API = "https://api.telegram.org/bot{token}/{method}"

# 입력창 아래에 늘 떠 있는 버튼. Worker 가 답할 때만 붙이고 있어서,
# 봇에게 글자를 안 치면 버튼이 안 생겼습니다. 매일 오는 이 메시지에도 붙입니다.
# (worker/src/index.js 의 KEYS 와 같은 내용이어야 합니다)
KEYS = json.dumps(
    {
        "keyboard": [[{"text": "📄 초안 만들기"}, {"text": "🎬 릴스 만들기"}]],
        "is_persistent": True,
        "resize_keyboard": True,
        "input_field_placeholder": "고쳐: 제목 더 짧게  — 처럼 고칠 곳을 적어도 됩니다",
    },
    ensure_ascii=False,
)


def pick_slug() -> str:
    """번호를 안 주면 '후기가 가장 많은, 아직 영상 안 만든 초안' 을 고릅니다.

    그냥 최근 것을 쓰면 신간이 걸리기 쉽습니다. 신간은 웹 자료가 500자 남짓이라
    내용이 얕습니다. 많이 읽힌 책일수록 자료가 두툼하고(실측: 사피엔스 2,306자 대
    신간 516자) 사람들이 아는 책이라 릴스 반응도 낫습니다.

    한 번 영상으로 만든 초안은 post.json 에 reel_at 이 찍혀 다시 안 걸립니다.
    남은 게 없으면 그때는 후기 많은 순으로 다시 돕니다.
    """
    rows = []
    for d in POSTS.iterdir():
        f = d / "post.json"
        if not d.is_dir() or not f.exists():
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append(
            {
                "slug": d.name,
                "reviews": int(p.get("review_count") or 0),
                "reeled": bool(p.get("reel_at")),
                # 카드뉴스로 이미 올린 책도 재탕입니다. 형식만 다를 뿐 같은 책입니다.
                # hand_posted 는 릴스를 손으로 인스타에 올리신 것. 봇은 그걸 알 수
                # 없어서 텔레그램에서 '올렸어' 라고 알려주시면 여기 표시됩니다.
                "posted": bool(p.get("published") or p.get("hand_posted")),
                "skipped": bool(p.get("skipped")),
            }
        )
    if not rows:
        return ""

    # 아직 아무 데도 안 쓴 책 → 릴스만 안 쓴 책 → 그래도 없으면 전부
    layers = [
        ("아직 안 쓴 책", [r for r in rows if not r["reeled"] and not r["posted"] and not r["skipped"]]),
        ("릴스만 안 만든 책", [r for r in rows if not r["reeled"]]),
        ("전부", rows),
    ]
    for label, pool in layers:
        if pool:
            pool.sort(key=lambda r: (r["reviews"], r["slug"]), reverse=True)
            pick = pool[0]
            print(f"고른 초안: {pick['slug']} (후기 {pick['reviews']}개, {label})")
            if label != "아직 안 쓴 책":
                print("  ! 새 책이 없어 이미 쓴 책에서 골랐습니다. 초안을 더 만드세요.")
            return pick["slug"]
    return ""


def last_reeled() -> str:
    """가장 최근에 영상을 만든 초안. '고쳐 주세요' 요청은 이걸 다시 만듭니다."""
    best, when = "", ""
    for d in POSTS.iterdir():
        f = d / "post.json"
        if not d.is_dir() or not f.exists():
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if p.get("reel_at") and p["reel_at"] > when:
            best, when = d.name, p["reel_at"]
    return best


def mark_done(slug: str) -> None:
    """이 초안으로 영상을 만들었다고 표시합니다. 다음에 같은 책이 또 걸리지 않게."""
    f = POSTS / slug / "post.json"
    p = json.loads(f.read_text(encoding="utf-8"))
    p["reel_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat(timespec="seconds")
    f.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def send(video: Path, post: dict, caption: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("텔레그램 열쇠가 없어 보내지 않습니다. 파일만 남깁니다.")
        return

    note = (
        f"🎬 {post.get('short_title') or post.get('title','')}\n"
        f"{post.get('author','')}\n\n"
        "음악 없이 읽는 소리만 들어 있습니다.\n"
        "인스타 앱에서 음악을 붙여 올려주세요."
    )
    with video.open("rb") as f:
        r = requests.post(
            API.format(token=token, method="sendVideo"),
            data={"chat_id": chat, "caption": note, "supports_streaming": True},
            files={"video": (video.name, f, "video/mp4")},
            timeout=300,
        )
    if r.status_code != 200 or not r.json().get("ok"):
        raise RuntimeError(f"텔레그램 전송 실패: {r.text[:300]}")
    print("텔레그램으로 보냈습니다.")

    # 캡션은 따로 보냅니다. 영상 설명에 붙이면 길이 제한에 걸리고,
    # 무엇보다 통째로 복사하기가 불편합니다.
    if caption:
        requests.post(
            API.format(token=token, method="sendMessage"),
            data={
                "chat_id": chat,
                "text": caption,
                "disable_web_page_preview": True,
                "reply_markup": KEYS,
            },
            timeout=60,
        )
        print("캡션도 보냈습니다.")


def make_one(slug: str, note: str, config: dict) -> bool:
    path = POSTS / slug / "post.json"
    if not path.exists():
        print(f"초안을 찾을 수 없습니다: {slug}")
        return False

    post = json.loads(path.read_text(encoding="utf-8"))
    print(f"릴스를 만듭니다: {slug} — {post.get('short_title') or post.get('title','')}")
    out = POSTS / slug / "reel.mp4"
    made = reel.make_reel(post, config, out, note)
    send(out, post, made.get("caption", ""))
    # 표시를 남겨야 다음에 같은 책이 또 걸리지 않습니다.
    # 한 번에 여러 개 만들 때 특히 중요합니다.
    mark_done(slug)
    # 영상 파일은 저장소에 넣지 않습니다(.gitignore). 텔레그램에 보낸 것으로 충분합니다.
    print(f"파일: {out}")
    return True


def main() -> int:
    note = (os.environ.get("REEL_NOTE") or "").strip()
    slug = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("REEL_SLUG", "")
    slug = slug.strip()
    count = max(1, int(os.environ.get("REEL_COUNT") or 1))
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    if note:
        print(f"고쳐 달라는 요청: {note}")
    if slug:
        # 번호를 콕 집어 주셨으면 그 하나만 만듭니다.
        return 0 if make_one(slug, note, config) else 1

    # 여러 개를 한 작업 안에서 만듭니다. 요청을 여러 번 보내면 GitHub 가
    # 줄 세우면서 앞의 것을 취소해 버려 몇 개만 남습니다.
    made = 0
    for n in range(count):
        pick = (last_reeled() if note and n == 0 else "") or pick_slug()
        if not pick:
            print("더 만들 초안이 없습니다.")
            break
        print(f"=== {n+1}/{count} ===")
        if make_one(pick, note, config):
            made += 1
    print(f"모두 {made}개 만들었습니다.")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
