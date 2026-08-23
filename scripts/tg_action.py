"""텔레그램에서 온 명령 한 건을 즉시 처리합니다.

'버튼 확인' 워크플로는 텔레그램에 계속 물어보는 방식이라 최대 한 시간이 걸립니다.
이 스크립트는 웹훅(Cloudflare Worker)이 깨워주면 그 자리에서 한 건만 처리합니다.
누르고 1분 안에 끝납니다.

물어보지 않고 바로 처리한다는 것만 다르고, 발행·건너뜀·메시지 바꾸기는
watch_buttons.py 의 것을 그대로 씁니다. 두 벌로 나뉘면 한쪽만 고치는 사고가 납니다.

환경변수
  TG_ACTION      publish 또는 skip
  TG_SLUG        초안 번호 (예: 20260806-2)
  TG_CHAT_ID     텔레그램 대화방 번호
  TG_MESSAGE_ID  바꿔줄 메시지 번호
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import watch_buttons  # noqa: E402


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN 이 없습니다.")
        return 1

    action = os.environ.get("TG_ACTION", "")
    slug = os.environ.get("TG_SLUG", "")

    # 카드뉴스를 끈 뒤로는 인스타에 올리지 않습니다.
    # 예전 텔레그램 메시지에 남아 있는 '승인하고 올리기' 버튼은 아직 살아 있어서,
    # 실수로 누르면 옛 카드가 올라갑니다. 여기서 막습니다.
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if action == "publish" and not config.get("발행", {}).get("카드_만들기", True):
        print("카드뉴스 발행은 꺼져 있습니다. 올리지 않습니다.")
        chat = os.environ.get("TG_CHAT_ID", "")
        if token and chat:
            import requests

            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={
                    "chat_id": chat,
                    "text": (
                        "카드뉴스 발행은 꺼져 있습니다. 지금은 릴스만 만듭니다. "
                        "다시 켜려면 config.json 의 발행.카드_만들기 를 true 로 바꾸세요."
                    ),
                },
                timeout=30,
            )
        return 0
    if action not in ("publish", "skip") or not slug:
        print(f"무엇을 할지 알 수 없습니다: action={action!r} slug={slug!r}")
        return 1

    # watch_buttons.handle() 이 그대로 받을 수 있게 텔레그램 응답 모양으로 맞춰줍니다.
    # callback_query_id 는 이미 Worker 가 답해버렸으므로 여기서는 쓰이지 않습니다.
    update = {
        "callback_query": {
            "id": "webhook",
            "data": f"{'pub' if action == 'publish' else 'skip'}:{slug}",
            "message": {
                "chat": {"id": int(os.environ["TG_CHAT_ID"])},
                "message_id": int(os.environ["TG_MESSAGE_ID"]),
            },
        }
    }
    watch_buttons.handle(update, token, os.environ.get("GITHUB_REPOSITORY", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
