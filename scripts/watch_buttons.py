"""텔레그램에서 누른 버튼을 받아 처리합니다.

'✅ 승인하고 올리기' 를 누르면 그 자리에서 발행하고, 메시지를 결과로 바꿔줍니다.
'✕ 버리기' 를 누르면 그 초안을 넘깁니다.

서버 없이 동작합니다. 텔레그램에 "새 버튼 눌림 있나요?" 하고 물어보는 방식(long polling)이라,
지정한 시간(WATCH_MINUTES) 동안만 지켜봅니다. 그 시간이 지나 누른 것은
'버튼 확인' 워크플로를 한 번 돌리면 그때 처리됩니다.

★ 이 봇 토큰은 신간 극장 전용이어야 합니다.
  다른 봇과 공유하면 서로 버튼 눌림을 가져가 양쪽 다 망가집니다.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.publish import POSTS, publish_slug  # noqa: E402

API = "https://api.telegram.org/bot{token}/{method}"
LONG_POLL = 50  # 텔레그램에 한 번 물어보고 기다리는 초


def call(method: str, data: dict, token: str, timeout: int = 70) -> dict:
    resp = requests.post(API.format(token=token, method=method), data=data, timeout=timeout)
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패: {str(payload)[:200]}")
    return payload


def answer(token: str, query_id: str, text: str) -> None:
    try:
        call("answerCallbackQuery", {"callback_query_id": query_id, "text": text[:200]}, token)
    except (requests.RequestException, RuntimeError):
        pass


def replace_message(token: str, chat_id: int, message_id: int, text: str) -> None:
    """버튼을 없애고 결과 문구로 바꿔, 두 번 누르는 실수를 막습니다."""
    try:
        call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": text},
            token,
        )
    except (requests.RequestException, RuntimeError):
        pass


def mark_skipped(slug: str) -> None:
    path = POSTS / slug / "post.json"
    if not path.exists():
        return
    post = json.loads(path.read_text(encoding="utf-8"))
    post["skipped"] = True
    path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")


def commit(message: str) -> None:
    for args in (
        ["git", "config", "user.name", "book-bot"],
        ["git", "config", "user.email", "book-bot@users.noreply.github.com"],
        ["git", "add", "posts"],
    ):
        subprocess.run(args, cwd=ROOT, capture_output=True)
    staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"], cwd=ROOT, capture_output=True
    )
    if staged.returncode == 0:
        return  # 바뀐 게 없음
    subprocess.run(["git", "commit", "-m", message], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "pull", "--rebase", "-q"], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, capture_output=True)


def handle(update: dict, token: str, repo: str) -> bool:
    q = update.get("callback_query")
    if not q:
        return False
    data = q.get("data", "")
    if ":" not in data:
        return False

    action, slug = data.split(":", 1)
    chat_id = q["message"]["chat"]["id"]
    message_id = q["message"]["message_id"]

    if action == "skip":
        mark_skipped(slug)
        commit(f"건너뜀 {slug}")
        answer(token, q["id"], "넘겼습니다")
        replace_message(token, chat_id, message_id, f"✕ {slug} — 올리지 않았습니다")
        print(f"건너뜀: {slug}")
        return True

    if action != "pub":
        return False

    answer(token, q["id"], "올리는 중입니다...")
    try:
        out = publish_slug(slug, repo)
    except Exception as exc:
        print(f"발행 실패 {slug}: {exc}")
        replace_message(token, chat_id, message_id, f"⚠️ {slug} 발행 실패\n\n{exc}")
        return True

    commit(f"발행 {slug}")
    where = ", ".join(out["results"])
    replace_message(
        token, chat_id, message_id, f"✅ 올렸습니다 — {out['title']}\n({where})"
    )
    print(f"발행 완료: {slug} → {out['results']}")
    return True


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    minutes = int(os.environ.get("WATCH_MINUTES") or 30)
    if not token:
        print("TELEGRAM_BOT_TOKEN 이 없습니다.")
        return 0

    deadline = time.time() + minutes * 60
    offset = None
    handled = 0
    # flush 를 켜야 로그가 실시간으로 보입니다. 안 그러면 끝날 때 한꺼번에 나옵니다.
    print(f"버튼을 {minutes}분 동안 기다립니다.", flush=True)
    next_beat = time.time() + 600

    while time.time() < deadline:
        if time.time() >= next_beat:
            left = int((deadline - time.time()) / 60)
            print(f"  ...대기 중 (남은 시간 {left}분, 처리 {handled}건)", flush=True)
            next_beat = time.time() + 600

        params = {"timeout": LONG_POLL, "allowed_updates": json.dumps(["callback_query"])}
        if offset is not None:
            params["offset"] = offset
        try:
            updates = call("getUpdates", params, token, timeout=LONG_POLL + 20).get("result", [])
        except (requests.RequestException, RuntimeError) as exc:
            print(f"  조회 실패(계속 시도): {exc}")
            time.sleep(5)
            continue

        for u in updates:
            offset = u["update_id"] + 1
            if handle(u, token, repo):
                handled += 1

    print(f"끝. 처리한 버튼 {handled}건.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
