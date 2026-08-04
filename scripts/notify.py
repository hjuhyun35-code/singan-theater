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


def buttons(slug: str) -> str:
    """승인 / 버리기 버튼. 누르면 '버튼 확인' 워크플로가 받아 처리합니다."""
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": "✅ 승인하고 올리기", "callback_data": f"pub:{slug}"},
                    {"text": "✕ 버리기", "callback_data": f"skip:{slug}"},
                ]
            ]
        }
    )


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
    # 판정("얕다")이 아니라 사실만 적습니다. 판단은 보는 사람 몫입니다.
    notes = [f"원문 소개글 {post.get('source_len', 0)}자"]
    if post.get("toc_len"):
        notes.append(f"목차 {post['toc_len']}자")
    if post.get("copy_overlap", 0) >= 22:
        notes.append(f"원문과 {post['copy_overlap']}자 겹침 — 손보는 게 좋습니다")
    lines += ["", " · ".join(notes)]
    lines += ["", "─" * 20, f"{post['slug']}"]
    return "\n".join(lines)


def main() -> int:
    # 텔레그램 설정이 없어도 초안 만들기 자체는 성공으로 끝나야 합니다.
    # (카드는 Actions 화면의 첨부파일에서 볼 수 있습니다)
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        print("텔레그램 설정이 없어 알림을 건너뜁니다.")
        print("  → BotFather 에서 토큰을 받아 TELEGRAM_BOT_TOKEN 시크릿에 넣으세요.")
        return 0

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
        # 앨범에는 버튼을 못 붙입니다. 카드를 먼저 보내고, 버튼은 그 아래 붙입니다.
        if images:
            send_album(chat_id, images, text)
            _call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "올릴까요?",
                    "reply_markup": buttons(slug),
                },
            )
        else:
            _call(
                "sendMessage",
                {"chat_id": chat_id, "text": text, "reply_markup": buttons(slug)},
            )
        print(f"보냄: {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
