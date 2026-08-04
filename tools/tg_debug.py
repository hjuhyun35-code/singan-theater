"""텔레그램 쪽에 무엇이 와 있는지 그대로 보여줍니다.

버튼을 눌렀는데 아무 일도 안 일어날 때 원인을 찾는 용도입니다.
읽기만 하고 아무것도 처리하지 않습니다(offset 을 넘기지 않아 눌린 건 그대로 남습니다).
"""

import json
import os
import sys

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def call(method: str, params: dict | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.get(API.format(token=token, method=method), params=params or {}, timeout=40)
    return r.json()


def main() -> int:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("TELEGRAM_BOT_TOKEN 이 없습니다.")
        return 1

    me = call("getMe")
    if me.get("ok"):
        u = me["result"]
        print(f"이 토큰의 봇 : @{u.get('username')}  ({u.get('first_name')})")
    else:
        print("getMe 실패:", str(me)[:200])
        return 1

    hook = call("getWebhookInfo")
    if hook.get("ok"):
        info = hook["result"]
        url = info.get("url") or "(없음)"
        print(f"웹훅        : {url}")
        if info.get("url"):
            print("  ⚠️ 웹훅이 걸려 있으면 버튼 눌림이 그쪽으로만 갑니다.")
            print("     우리 방식(getUpdates)으로는 아무것도 못 받습니다.")
        print(f"대기 중인 업데이트: {info.get('pending_update_count')}건")

    print("\n=== 지금 대기 중인 것 (처리하지 않고 보기만) ===")
    got = call("getUpdates", {"timeout": 2, "limit": 20})
    if not got.get("ok"):
        print("getUpdates 실패:", str(got)[:300])
        return 1

    updates = got.get("result", [])
    if not updates:
        print("없습니다.")
        print("\n원인 후보:")
        print("  · 다른 프로그램이 같은 봇 토큰으로 먼저 가져갔다 (가장 흔함)")
        print("  · 버튼이 달린 메시지를 '다른 봇'이 보냈다 (토큰 바꾸기 전 메시지)")
        print("  · 아직 안 눌렀다")
        return 0

    for u in updates:
        kind = "callback_query" if "callback_query" in u else next(iter(u.keys() - {"update_id"}), "?")
        line = f"  #{u['update_id']} {kind}"
        if "callback_query" in u:
            q = u["callback_query"]
            line += f"  data={q.get('data')!r}"
            line += f"  보낸봇메시지id={q.get('message', {}).get('message_id')}"
        print(line)
    print(f"\n총 {len(updates)}건. 이 상태로 '버튼 확인' 을 돌리면 처리됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
