"""키를 입력받아 .env 에 안전하게 저장합니다.

메모장으로 직접 고치다 실수하는 것보다 확실합니다.
입력한 키는 화면에 찍히지 않고, 저장 후에는 끝 4자리만 보여줍니다.

  .venv\\Scripts\\python.exe tools\\set_key.py            # 비어 있는 키를 차례로 물어봄
  .venv\\Scripts\\python.exe tools\\set_key.py 알라딘      # 특정 키만 다시 넣기
"""

import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.settings import env  # noqa: E402
from tools.refresh_tokens import _write_env  # noqa: E402

# (별명, 환경변수명, 설명, 받는 곳)
KEYS = [
    ("알라딘", "ALADIN_TTB_KEY", "알라딘 TTB 키 (ttb 로 시작)",
     "https://www.aladin.co.kr/ttb/wblog_manage.aspx"),
    ("클로드", "ANTHROPIC_API_KEY", "Claude API 키 (sk-ant- 로 시작)",
     "https://console.anthropic.com/settings/keys"),
    ("국중", "NL_API_KEY", "국립중앙도서관 서지정보 인증키 (목차·책소개)",
     "https://www.nl.go.kr/NL/contents/N31101010000.do"),
    ("이미지", "IMGBB_API_KEY", "imgbb 이미지 호스팅 키",
     "https://api.imgbb.com/"),
    ("쓰레드앱", "THREADS_APP_ID", "쓰레드 Meta 앱 ID", "developers.facebook.com"),
    ("쓰레드시크릿", "THREADS_APP_SECRET", "쓰레드 Meta 앱 시크릿", "developers.facebook.com"),
    ("인스타앱", "INSTAGRAM_APP_ID", "인스타 Meta 앱 ID (glassnegative-bot)", "developers.facebook.com"),
    ("인스타시크릿", "INSTAGRAM_APP_SECRET", "인스타 Meta 앱 시크릿 (glassnegative-bot)", "developers.facebook.com"),
]

# 붙여넣기 실수를 잡아내기 위한 최소한의 형태 검사
PREFIX = {"ALADIN_TTB_KEY": "ttb", "ANTHROPIC_API_KEY": "sk-ant-"}


def _clean(raw: str) -> str:
    """따옴표, 앞뒤 공백, 실수로 같이 복사된 'KEY=' 앞부분을 떼어냅니다."""
    v = raw.strip().strip('"').strip("'").strip()
    if "=" in v and v.split("=", 1)[0].isupper():
        v = v.split("=", 1)[1].strip()
    return v


def ask(label: str, name: str, desc: str, where: str) -> bool:
    current = env(name)
    state = f"지금: …{current[-4:]} (이미 있음)" if current else "지금: 비어 있음"
    print(f"\n── {label} ──  {desc}")
    print(f"   받는 곳: {where}")
    print(f"   {state}")
    print("   붙여넣고 Enter. 그냥 Enter 치면 건너뜁니다.")
    print("   (보안을 위해 입력한 글자는 화면에 보이지 않습니다)")

    value = _clean(getpass("   > "))
    if not value:
        print("   건너뜀")
        return False

    expected = PREFIX.get(name)
    if expected and not value.startswith(expected):
        print(f"   ⚠ '{expected}' 로 시작하지 않습니다. 다른 키를 붙여넣으신 것 같습니다.")
        if input("   그래도 저장할까요? (y/n) ").strip().lower() != "y":
            print("   저장하지 않았습니다.")
            return False

    _write_env(name, value)
    print(f"   저장 완료 — {len(value)}자, 끝 4자리 …{value[-4:]}")
    return True


def main() -> int:
    if not (ROOT / ".env").exists():
        print(".env 파일이 없습니다. .env.example 을 복사해 .env 로 만들어 주세요.")
        return 1

    wanted = sys.argv[1:]
    targets = [k for k in KEYS if not wanted or k[0] in wanted]
    if wanted and not targets:
        print(f"그런 이름은 없습니다. 쓸 수 있는 이름: {', '.join(k[0] for k in KEYS)}")
        return 2

    if not wanted:
        targets = [k for k in targets if not env(k[1])] or targets
        print("비어 있는 키를 차례로 물어봅니다. 지금 없는 것은 Enter 로 넘기세요.")

    saved = sum(ask(*t) for t in targets)
    print(f"\n{saved}개 저장했습니다.")
    print("이어서 설정확인.bat 을 실행해 실제로 동작하는지 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
