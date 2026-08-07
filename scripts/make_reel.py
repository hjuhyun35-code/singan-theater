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


def latest_slug() -> str:
    """번호를 안 주면 가장 최근 초안을 씁니다."""
    dirs = sorted((d for d in POSTS.iterdir() if d.is_dir()), reverse=True)
    return dirs[0].name if dirs else ""


def send(video: Path, post: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("텔레그램 열쇠가 없어 보내지 않습니다. 파일만 남깁니다.")
        return
    caption = (
        f"🎬 {post.get('short_title') or post.get('title','')}\n"
        f"{post.get('author','')}\n\n"
        "음악 없이 읽는 소리만 들어 있습니다.\n"
        "인스타 앱에서 음악을 붙여 올려주세요."
    )
    with video.open("rb") as f:
        r = requests.post(
            API.format(token=token, method="sendVideo"),
            data={"chat_id": chat, "caption": caption, "supports_streaming": True},
            files={"video": (video.name, f, "video/mp4")},
            timeout=300,
        )
    if r.status_code != 200 or not r.json().get("ok"):
        raise RuntimeError(f"텔레그램 전송 실패: {r.text[:300]}")
    print("텔레그램으로 보냈습니다.")


def main() -> int:
    slug = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("REEL_SLUG", "")
    slug = slug.strip() or latest_slug()
    path = POSTS / slug / "post.json"
    if not path.exists():
        print(f"초안을 찾을 수 없습니다: {slug}")
        return 1

    post = json.loads(path.read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    print(f"릴스를 만듭니다: {slug} — {post.get('short_title') or post.get('title','')}")

    out = POSTS / slug / "reel.mp4"
    reel.make_reel(post, config, out)
    send(out, post)

    # 영상은 저장소에 넣지 않습니다. 매일 쌓이면 저장소가 금방 무거워집니다.
    # 텔레그램에 보낸 것으로 충분하고, 필요하면 다시 만들면 됩니다.
    print(f"파일: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
