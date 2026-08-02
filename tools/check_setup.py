"""설정이 제대로 됐는지 하나씩 확인합니다.

키를 채운 뒤 이 파일을 먼저 실행하세요. 어디가 잘못됐는지 바로 알려줍니다.
  .venv\\Scripts\\python.exe tools\\check_setup.py
"""

import base64
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.settings import env, load_config  # noqa: E402

OK, FAIL, SKIP = "  [정상]", "  [실패]", "  [미설정]"

# 1x1 투명 PNG. 업로드 테스트용.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def check_env_file() -> bool:
    if not (ROOT / ".env").exists():
        print(FAIL, ".env 파일이 없습니다.")
        print("        → .env.example 을 복사해 이름을 .env 로 바꾸고 키를 채우세요.")
        return False
    print(OK, ".env 파일 있음")
    return True


def check_config() -> bool:
    try:
        config = load_config()
        genres = ", ".join(g["이름"] for g in config["분야"]["목록"])
        print(OK, f"config.json 읽음 — 분야: {genres} / 하루 {config['수집']['하루_초안수']}건")
        return True
    except Exception as exc:
        print(FAIL, f"config.json 오류: {exc}")
        return False


def check_aladin() -> bool:
    if not env("ALADIN_TTB_KEY"):
        print(SKIP, "알라딘 — ALADIN_TTB_KEY 가 비어 있습니다")
        return False
    from src.aladin import fetch_list, normalize

    try:
        items = fetch_list("ItemNewSpecial", 336, 3)
        if not items:
            print(FAIL, "알라딘 — 응답은 왔지만 책이 0권입니다. 키를 확인하세요.")
            return False
        print(OK, f"알라딘 — 신간 {len(items)}권 확인 (예: {normalize(items[0])['title']})")
        return True
    except Exception as exc:
        print(FAIL, f"알라딘 — {exc}")
        return False


def check_anthropic() -> bool:
    if not env("ANTHROPIC_API_KEY"):
        print(SKIP, "Claude — ANTHROPIC_API_KEY 가 비어 있습니다")
        return False
    try:
        from anthropic import Anthropic

        config = load_config()
        client = Anthropic(api_key=env("ANTHROPIC_API_KEY"))
        client.messages.create(
            model=config["모델"]["이름"],
            max_tokens=8,
            messages=[{"role": "user", "content": "안녕"}],
        )
        print(OK, f"Claude — {config['모델']['이름']} 호출 성공")
        return True
    except Exception as exc:
        print(FAIL, f"Claude — {exc}")
        return False


def check_imgbb() -> bool:
    if not env("IMGBB_API_KEY"):
        print(SKIP, "이미지 호스팅 — IMGBB_API_KEY 가 비어 있습니다")
        return False
    try:
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": env("IMGBB_API_KEY"),
                "image": base64.b64encode(TINY_PNG).decode(),
                "expiration": 60,
            },
            timeout=40,
        )
        data = resp.json()
        if not data.get("success"):
            print(FAIL, f"이미지 호스팅 — {data}")
            return False
        print(OK, "이미지 호스팅 — 업로드 성공")
        return True
    except Exception as exc:
        print(FAIL, f"이미지 호스팅 — {exc}")
        return False


def _check_meta(label: str, host: str, token_key: str, id_key: str) -> bool:
    token = env(token_key)
    if not token:
        print(SKIP, f"{label} — {token_key} 가 비어 있습니다")
        return False
    try:
        resp = requests.get(
            f"{host}/me", params={"fields": "id,username", "access_token": token}, timeout=30
        )
        data = resp.json()
        if "error" in data:
            msg = data["error"].get("message", "")
            print(FAIL, f"{label} — {msg}")
            if data["error"].get("code") in (190, 102):
                print("        → 토큰 만료. tools\\refresh_tokens.py 를 실행하세요.")
            return False
        saved_id = env(id_key)
        if saved_id and saved_id != data.get("id"):
            print(FAIL, f"{label} — .env 의 {id_key}({saved_id})가 실제 ID({data['id']})와 다릅니다")
            return False
        print(OK, f"{label} — @{data.get('username', '?')} (ID {data.get('id')})")
        return True
    except Exception as exc:
        print(FAIL, f"{label} — {exc}")
        return False


def check_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        print(OK, "카드 렌더링 — 크롬 준비됨")
        return True
    except Exception as exc:
        print(FAIL, f"카드 렌더링 — {exc}")
        print("        → .venv\\Scripts\\python.exe -m playwright install chromium")
        return False


def main() -> int:
    print("\n설정 점검\n" + "-" * 52)
    results = {
        ".env 파일": check_env_file(),
        "config.json": check_config(),
        "알라딘": check_aladin(),
        "Claude": check_anthropic(),
        "이미지 호스팅": check_imgbb(),
        "쓰레드": _check_meta(
            "쓰레드", "https://graph.threads.net/v1.0", "THREADS_ACCESS_TOKEN", "THREADS_USER_ID"
        ),
        "인스타그램": _check_meta(
            "인스타그램", "https://graph.instagram.com/v23.0", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"
        ),
        "카드 렌더링": check_playwright(),
    }
    print("-" * 52)

    core = ["알라딘", "Claude", "카드 렌더링"]
    if all(results[k] for k in core):
        print("초안 만들기는 지금 바로 됩니다. (실행.bat)")
    else:
        missing = [k for k in core if not results[k]]
        print(f"초안을 만들려면 먼저 해결해야 합니다: {', '.join(missing)}")

    post = ["이미지 호스팅", "쓰레드", "인스타그램"]
    ready = [k for k in post if results[k]]
    print(f"발행 준비된 곳: {', '.join(ready) if ready else '없음'}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
