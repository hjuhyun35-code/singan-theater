"""인스타 토큰이 살아 있는지, 발행 권한이 있는지 확인합니다.

토큰 값은 출력하지 않습니다. 발행은 하지 않습니다.
"""

import json
import os
import sys

import requests

HOST = "https://graph.instagram.com/v23.0"


def call(label: str, path: str, params: dict, token: str) -> dict | None:
    resp = requests.get(f"{HOST}/{path}", params={**params, "access_token": token}, timeout=30)
    data = {}
    try:
        data = resp.json()
    except ValueError:
        print(f"  [{label}] HTTP {resp.status_code} — JSON 아님: {resp.text[:200]}")
        return None
    if "error" in data:
        err = data["error"]
        print(f"  [{label}] 실패 — {err.get('message')} (code={err.get('code')})")
        return None
    print(f"  [{label}] 정상 — {json.dumps(data, ensure_ascii=False)[:220]}")
    return data


def main() -> int:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    uid = os.environ.get("INSTAGRAM_USER_ID", "")
    secret = os.environ.get("INSTAGRAM_APP_SECRET", "")
    app_id = os.environ.get("INSTAGRAM_APP_ID", "")

    print("설정 상태")
    print(f"  토큰       : {'있음 (' + str(len(token)) + '자)' if token else '없음'}")
    print(f"  계정 ID    : {uid or '없음'}")
    print(f"  앱 ID      : {'있음' if app_id else '없음'}")
    print(f"  앱 시크릿  : {'있음' if secret else '없음'}")
    if not token or not uid:
        print("\n토큰이나 계정 ID가 없습니다.")
        return 1

    print("\n확인 중...")
    me = call("계정 조회", "me", {"fields": "id,username,account_type"}, token)
    limit = call("발행 한도", f"{uid}/content_publishing_limit", {"fields": "quota_usage,config"}, token)

    print()
    if me is None:
        print("토큰이 죽었거나 접근이 막혔습니다.")
        print("  → Meta 대시보드에서 토큰을 새로 생성해 INSTAGRAM_ACCESS_TOKEN 을 수정하세요.")
        print("  → 새 토큰으로도 같은 오류면 계정 제한일 수 있습니다 (인스타 앱 알림 확인).")
        return 1

    if me.get("id") != uid:
        print(f"⚠ 계정 ID가 다릅니다. 저장된 값 {uid} / 실제 {me.get('id')}")
        print("  → INSTAGRAM_USER_ID 를 실제 값으로 고치세요.")
        return 1

    kind = me.get("account_type", "")
    if kind and kind not in ("BUSINESS", "MEDIA_CREATOR"):
        print(f"⚠ 계정 종류가 {kind} 입니다. 프로페셔널(크리에이터)로 전환해야 발행됩니다.")
        return 1

    if limit is None:
        print("계정 조회는 되는데 발행 권한 확인이 안 됩니다.")
        print("  → instagram_business_content_publish 권한을 확인하세요.")
        return 1

    print(f"발행 준비 완료 — @{me.get('username')} ({kind or '종류 미표시'})")
    if not secret:
        print("\n※ 앱 시크릿이 없어 60일 토큰 교환을 못 합니다. 지금 토큰이 만료되면 또 멈춥니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
