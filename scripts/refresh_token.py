"""토큰이 살아 있는지 매주 확인합니다.

토큰은 60일이면 만료되고, 만료되면 발행이 조용히 멈춥니다.
그 '조용히'가 문제라서, 죽는 즉시 텔레그램으로 알려줍니다.

두 가지 모드로 동작합니다.
  · GH_TOKEN 이 없을 때(기본)  — 확인만 하고, 문제가 있으면 알림
  · GH_TOKEN 이 있을 때        — 60일 연장까지 자동으로 하고 시크릿을 갱신

기본 모드로도 목적(조용한 중단 방지)은 달성됩니다.
완전 자동으로 하고 싶으면 Secrets 쓰기 권한이 있는 PAT 를 GH_PAT 에 넣으세요.

토큰 값은 화면에 절대 찍지 않습니다. gh 로 넘길 때도 표준입력을 씁니다.
"""

import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TIMEOUT = 30

PLATFORMS = [
    {
        "label": "인스타그램",
        "host": "https://graph.instagram.com",
        "grant": "ig_refresh_token",
        "secret": "INSTAGRAM_ACCESS_TOKEN",
        "me": "https://graph.instagram.com/v23.0/me",
    },
    {
        "label": "쓰레드",
        "host": "https://graph.threads.net",
        "grant": "th_refresh_token",
        "secret": "THREADS_ACCESS_TOKEN",
        "me": "https://graph.threads.net/v1.0/me",
    },
]

# 남은 기간이 이보다 적으면 경고를 보냅니다
WARN_DAYS = 20


def refresh(host: str, grant: str, token: str) -> tuple[str, int]:
    resp = requests.get(
        f"{host}/refresh_access_token",
        params={"grant_type": grant, "access_token": token},
        timeout=TIMEOUT,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(data.get("error", {}).get("message", str(data)[:200]))
    return data["access_token"], int(data.get("expires_in", 0)) // 86400


def store(name: str, value: str) -> None:
    """gh 로 시크릿을 덮어씁니다. 값은 표준입력으로만 넘깁니다."""
    repo = os.environ["GITHUB_REPOSITORY"]
    proc = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo],
        input=value,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"시크릿 저장 실패: {proc.stderr.strip()[:200]}")


def notify(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": text},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        pass


def alive(me_url: str, token: str) -> tuple[bool, str]:
    """토큰이 아직 쓸 수 있는지만 확인합니다. 아무것도 바꾸지 않습니다."""
    try:
        resp = requests.get(
            me_url, params={"fields": "id,username", "access_token": token}, timeout=TIMEOUT
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return False, str(exc)[:150]
    if "error" in data:
        return False, data["error"].get("message", "")[:150]
    return True, data.get("username", "")


def main() -> int:
    auto = bool(os.environ.get("GH_TOKEN"))
    print("모드:", "자동 연장" if auto else "확인만 (연장하려면 GH_PAT 필요)")

    problems: list[str] = []
    touched = 0

    for p in PLATFORMS:
        token = os.environ.get(p["secret"], "")
        if not token:
            print(f"[{p['label']}] 토큰이 없어 건너뜁니다.")
            continue

        if not auto:
            ok, info = alive(p["me"], token)
            if ok:
                touched += 1
                print(f"[{p['label']}] 정상 — @{info}")
            else:
                msg = f"[{p['label']}] 토큰이 동작하지 않습니다: {info}"
                print(msg)
                problems.append(msg)
            continue

        try:
            new_token, days = refresh(p["host"], p["grant"], token)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            msg = f"[{p['label']}] 갱신 실패: {exc}"
            print(msg)
            problems.append(msg)
            continue

        try:
            store(p["secret"], new_token)
        except RuntimeError as exc:
            msg = f"[{p['label']}] {exc}"
            print(msg)
            problems.append(msg)
            continue

        touched += 1
        print(f"[{p['label']}] 갱신 완료 — 앞으로 {days}일 유효")
        if days < WARN_DAYS:
            problems.append(f"[{p['label']}] 남은 기간이 {days}일뿐입니다")

    if problems:
        notify(
            "⚠️ 신간 극장 토큰 갱신 문제\n\n"
            + "\n".join(problems)
            + "\n\n그대로 두면 발행이 멈춥니다. 토큰을 새로 발급받으세요.\n"
            + "https://github.com/hjuhyun35-code/singan-theater/blob/main/발행안내.md"
        )
        return 1

    if touched == 0:
        print("확인할 토큰이 없었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
