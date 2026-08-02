"""만들어진 초안을 텔레그램으로 보냅니다.

카드 이미지를 앨범으로 묶어 보내고, 그 아래에 발행하는 방법을 적어 보냅니다.
폰에서 보고 마음에 들면 GitHub 에서 발행 워크플로만 돌리면 됩니다.
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

POSTS = ROOT / "posts"
API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 60


def _call(method: str, data: dict, files: dict | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(
        API.format(token=token, method=method), data=data, files=files, timeout=TIMEOUT
    )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패: {payload}")
    return payload


def send_album(chat_id: str, image_paths: list[Path], caption: str) -> None:
    """카드 이미지를 앨범 한 덩어리로 보냅니다. 최대 10장."""
    media, files = [], {}
    for i, path in enumerate(image_paths[:10]):
        key = f"photo{i}"
        item = {"type": "photo", "media": f"attach://{key}"}
        if i == 0:
            item["caption"] = caption[:1024]
        media.append(item)
        files[key] = (path.name, path.read_bytes(), "image/jpeg")
    _call(
        "sendMediaGroup",
        {"chat_id": chat_id, "media": json.dumps(media, ensure_ascii=False)},
        files,
    )


def summary(post: dict, repo: str) -> str:
    lines = [
        f"📖 {post['title']}",
        f"{post['author']} · {post['publisher']} · {post['pub_date']}",
        "",
        f"[캡션 첫 줄] {post['search_line']}",
        "",
        post["threads_text"][:600],
    ]
    warn = []
    if post.get("confidence") == "low":
        warn.append("⚠️ 자료가 빈약해 내용이 얕을 수 있습니다")
    if post.get("copy_overlap", 0) >= 22:
        warn.append(f"⚠️ 소개글과 {post['copy_overlap']}자 겹칩니다")
    if warn:
        lines += ["", *warn]
    lines += [
        "",
        "─" * 20,
        f"올리려면 슬러그: {post['slug']}",
        f"https://github.com/{repo}/actions/workflows/publish.yml",
        "→ Run workflow → slug 입력 → confirm 에 PUBLISH 입력",
    ]
    return "\n".join(lines)


def main() -> int:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    slugs = [s for s in (os.environ.get("SLUGS") or "").split(",") if s]

    if not slugs:
        _call("sendMessage", {"chat_id": chat_id, "text": "오늘은 새 초안이 없습니다."})
        print("초안 없음 — 알림만 보냈습니다.")
        return 0

    for slug in slugs:
        folder = POSTS / slug
        post = json.loads((folder / "post.json").read_text(encoding="utf-8"))
        images = [folder / c["file"] for c in post["cards"]]
        text = summary(post, repo)
        if images:
            send_album(chat_id, images, text)
        else:
            _call("sendMessage", {"chat_id": chat_id, "text": text})
        print(f"보냄: {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
