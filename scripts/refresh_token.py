"""인스타·쓰레드 토큰의 유효기간을 연장하고 GitHub Secrets 에 다시 넣습니다.

토큰은 60일이면 만료되고, 만료되면 발행이 조용히 멈춥니다.
매주 한 번 돌려서 항상 60일이 남아 있게 유지합니다.

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
    },
    {
        "label": "쓰레드",
        "host": "https://graph.threads.net",
        "grant": "th_refresh_token",
        "secret": "THREADS_ACCESS_TOKEN",
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


def main() -> int:
    if not os.environ.get("GH_TOKEN"):
        print("GH_TOKEN 이 없습니다. 시크릿을 저장할 권한이 없어 중단합니다.")
        print("  → 저장소 Secrets 에 GH_PAT 를 넣고 워크플로에 연결하세요.")
        return 1

    problems: list[str] = []
    touched = 0

    for p in PLATFORMS:
        token = os.environ.get(p["secret"], "")
        if not token:
            print(f"[{p['label']}] 토큰이 없어 건너뜁니다.")
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
        print("갱신할 토큰이 없었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
