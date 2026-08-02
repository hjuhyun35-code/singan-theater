"""Meta 대시보드에서 복사한 토큰을 받아 .env 에 저장합니다.

대시보드가 주는 토큰은 보통 1~2시간이면 죽습니다.
이 도구가 60일짜리 긴 토큰으로 바꿔주고, 계정 ID까지 알아내 저장합니다.
(이미 긴 토큰이면 그대로 확인만 하고 저장합니다.)

사용법:
  .venv\\Scripts\\python.exe tools\\setup_token.py instagram <대시보드에서_복사한_토큰>
  .venv\\Scripts\\python.exe tools\\setup_token.py instagram
      토큰을 생략하면 .env 에 이미 들어 있는 값을 씁니다.
      (직접 붙여넣은 짧은 토큰을 60일짜리로 바꾸고 계정 ID를 채울 때)
"""

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.settings import env  # noqa: E402
from tools.refresh_tokens import _write_env  # noqa: E402

PLATFORMS = {
    "threads": {
        "label": "쓰레드",
        "host": "https://graph.threads.net",
        "me": "https://graph.threads.net/v1.0/me",
        "grant": "th_exchange_token",
        "secret_key": "THREADS_APP_SECRET",
        "token_key": "THREADS_ACCESS_TOKEN",
        "id_key": "THREADS_USER_ID",
        "fields": "id,username",
    },
    "instagram": {
        "label": "인스타그램",
        "host": "https://graph.instagram.com",
        "me": "https://graph.instagram.com/v23.0/me",
        "grant": "ig_exchange_token",
        "secret_key": "INSTAGRAM_APP_SECRET",
        "token_key": "INSTAGRAM_ACCESS_TOKEN",
        "id_key": "INSTAGRAM_USER_ID",
        "fields": "id,username,account_type",
    },
}


def _exchange(cfg: dict, token: str, secret: str) -> tuple[str, int] | None:
    """짧은 토큰 -> 긴 토큰. 이미 긴 토큰이면 None 을 돌려줍니다."""
    resp = requests.get(
        f"{cfg['host']}/access_token",
        params={"grant_type": cfg["grant"], "client_secret": secret, "access_token": token},
        timeout=30,
    )
    data = resp.json()
    if "access_token" in data:
        return data["access_token"], int(data.get("expires_in", 0))
    print(f"  (긴 토큰으로 바꾸지 못했습니다: {data.get('error', {}).get('message', data)})")
    print("  → 이미 60일짜리 토큰일 수 있습니다. 받은 토큰 그대로 확인해 봅니다.")
    return None


def _verify(cfg: dict, token: str) -> dict | None:
    resp = requests.get(
        cfg["me"], params={"fields": cfg["fields"], "access_token": token}, timeout=30
    )
    data = resp.json()
    if "error" in data:
        print(f"  토큰이 동작하지 않습니다: {data['error'].get('message')}")
        return None
    return data


def main() -> int:
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in PLATFORMS:
        print(__doc__)
        return 2

    cfg = PLATFORMS[sys.argv[1]]
    if len(sys.argv) == 3:
        token = sys.argv[2].strip()
    else:
        token = env(cfg["token_key"])
        if not token:
            print(f"\n.env 의 {cfg['token_key']} 가 비어 있습니다.")
            print("대시보드에서 받은 토큰을 인자로 넘겨주세요.")
            return 1
        print(f"\n.env 에 있는 토큰을 사용합니다 (…{token[-4:]})")

    print(f"\n[{cfg['label']}] 토큰 설정 중...")

    secret = env(cfg["secret_key"])
    if secret:
        exchanged = _exchange(cfg, token, secret)
        if exchanged:
            token, expires = exchanged
            print(f"  긴 토큰으로 교환 완료 — {expires // 86400}일간 유효")
    else:
        print(f"  ({cfg['secret_key']} 가 비어 있어 교환을 건너뜁니다)")

    me = _verify(cfg, token)
    if me is None:
        return 1

    _write_env(cfg["token_key"], token)
    _write_env(cfg["id_key"], me["id"])

    print(f"  계정 확인: @{me.get('username', '?')} (ID {me['id']})")
    if me.get("account_type") and me["account_type"] not in ("BUSINESS", "MEDIA_CREATOR"):
        print(f"  ! 주의: 계정 종류가 {me['account_type']} 입니다.")
        print("    인스타 앱에서 프로페셔널(비즈니스/크리에이터) 계정으로 바꿔야 발행됩니다.")
    print(f"  .env 저장 완료 ({cfg['token_key']}, {cfg['id_key']})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
