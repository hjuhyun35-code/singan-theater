"""지금까지 무엇을 만들고 올렸는지 텔레그램으로 보내줍니다.

"이 책 전에 했던 거 아닌가?" 를 매번 저에게 묻지 않아도 되게 하려는 것입니다.
아무것도 바꾸지 않고 읽기만 합니다.

  python scripts/history.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
API = "https://api.telegram.org/bot{token}/{method}"
KST = timezone(timedelta(hours=9))


def when(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone(KST).strftime("%m/%d")
    except ValueError:
        return ""


def rows() -> list[dict]:
    out = []
    for d in sorted(POSTS.iterdir(), reverse=True):
        f = d / "post.json"
        if not d.is_dir() or not f.exists():
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "slug": d.name,
                "title": p.get("short_title") or p.get("title", ""),
                "author": p.get("author", ""),
                "reviews": int(p.get("review_count") or 0),
                "posted": when(p.get("published_at", "")),
                "reeled": when(p.get("reel_at", "")),
                "skipped": bool(p.get("skipped")),
            }
        )
    return out


def report(items: list[dict]) -> str:
    done = [r for r in items if r["posted"] or r["reeled"]]
    todo = [r for r in items if not r["posted"] and not r["reeled"] and not r["skipped"]]

    lines = [f"📚 지금까지 만든 것 {len(items)}권\n"]

    if done:
        lines.append("■ 쓴 책")
        for r in done:
            marks = []
            if r["posted"]:
                marks.append(f"카드 {r['posted']}")
            if r["reeled"]:
                marks.append(f"릴스 {r['reeled']}")
            lines.append(f"  · {r['title']} — {' / '.join(marks)}")
        lines.append("")

    if todo:
        lines.append("■ 아직 안 쓴 책 (릴스는 여기서 골라집니다)")
        for r in todo:
            lines.append(f"  · {r['title']} (후기 {r['reviews']})")
        lines.append("")
    else:
        lines.append("■ 아직 안 쓴 책이 없습니다. '초안 만들기' 를 눌러 새 책을 뽑으세요.\n")

    skipped = [r for r in items if r["skipped"]]
    if skipped:
        lines.append(f"■ 버린 것 {len(skipped)}권")

    return "\n".join(lines)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    items = rows()
    text = report(items)
    print(text)
    if not token or not chat:
        print("(텔레그램 열쇠가 없어 보내지는 않았습니다)")
        return 0

    # 텔레그램 한 통은 4096자까지입니다. 길면 잘라 나눠 보냅니다.
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3500:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)

    for c in chunks:
        requests.post(
            API.format(token=token, method="sendMessage"),
            data={"chat_id": chat, "text": c},
            timeout=60,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
