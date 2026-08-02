"""쓰레드/인스타 접속 토큰의 유효기간을 60일 연장합니다.

토큰은 60일이면 만료됩니다. 두 달에 한 번, 또는 발행이 실패할 때 실행하세요.
  .venv\\Scripts\\python.exe tools\\refresh_tokens.py

.env 파일의 토큰 값을 자동으로 새 값으로 바꿔줍니다.
"""

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.settings import env  # noqa: E402

ENV_PATH = ROOT / ".env"


def _refresh(host: str, grant_type: str, token: str) -> dict:
    resp = requests.get(
        f"{host}/refresh_access_token",
        params={"grant_type": grant_type, "access_token": token},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code >= 400 or "error" in data:
        raise RuntimeError(data.get("error", {}).get("message", resp.text[:200]))
    return data


def _write_env(key: str, value: str) -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(f"{key}={value}", text)
    else:
        text = text.rstrip() + f"\n{key}={value}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    jobs = [
        ("쓰레드", "THREADS_ACCESS_TOKEN", "https://graph.threads.net", "th_refresh_token"),
        ("인스타그램", "INSTAGRAM_ACCESS_TOKEN", "https://graph.instagram.com", "ig_refresh_token"),
    ]
    failed = 0
    for label, key, host, grant in jobs:
        token = env(key)
        if not token:
            print(f"[{label}] .env 에 {key} 가 비어 있어 건너뜁니다.")
            continue
        try:
            data = _refresh(host, grant, token)
            _write_env(key, data["access_token"])
            days = int(data.get("expires_in", 0)) // 86400
            print(f"[{label}] 갱신 완료. 앞으로 {days}일간 유효합니다.")
        except (requests.RequestException, RuntimeError, KeyError) as exc:
            failed += 1
            print(f"[{label}] 갱신 실패: {exc}")
            print(f"          → 토큰이 이미 만료됐다면 설정안내.md 를 보고 새로 발급받으세요.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
