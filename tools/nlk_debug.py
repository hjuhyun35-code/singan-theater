"""국중 API 가 실제로 무엇을 돌려주는지 그대로 보여줍니다.

수록률이 0 으로 나올 때 원인을 찾는 용도입니다.
인증키 승인 대기, 파라미터 오류, 응답 구조 변경 중 무엇인지 구분합니다.
"""

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nlk import HEADERS, SEARCH_URL  # noqa: E402
from src.settings import env  # noqa: E402

ISBN = sys.argv[1] if len(sys.argv) > 1 else "9791169852173"  # 창조적 습관


def show(label: str, params: dict) -> dict | None:
    key = env("NL_API_KEY")
    full = {"cert_key": key, "result_style": "json", "page_no": 1, "page_size": 5, **params}
    print(f"\n{'=' * 60}\n[{label}]")
    print("  보낸 값:", {k: ("***" if k == "cert_key" else v) for k, v in full.items()})
    try:
        r = requests.get(SEARCH_URL, params=full, headers=HEADERS, timeout=25)
    except requests.RequestException as exc:
        print("  요청 자체 실패:", exc)
        return None

    print(f"  상태 {r.status_code} / {r.headers.get('Content-Type')} / {len(r.text)}자")
    body = r.text.strip()
    print("  응답 앞부분:")
    print("   ", body[:700].replace("\n", "\n    "))

    try:
        data = r.json()
    except ValueError:
        print("  → JSON 이 아닙니다 (오류 페이지일 가능성)")
        return None

    print("  최상위 키:", list(data)[:12])
    if "docs" in data:
        docs = data["docs"] or []
        print(f"  docs 개수: {len(docs)}  (TOTAL_COUNT={data.get('TOTAL_COUNT')})")
        if docs:
            d = docs[0]
            print("  첫 항목 필드 수:", len(d))
            for k in sorted(d):
                v = str(d[k])
                if v.strip():
                    print(f"    {k:<26} {v[:70]}")
    return data


def main() -> int:
    if not env("NL_API_KEY"):
        print("NL_API_KEY 가 비어 있습니다.")
        return 1

    key = env("NL_API_KEY")
    print(f"인증키 길이 {len(key)}자, 끝 4자리 …{key[-4:]}")

    show("1) ISBN 으로 조회", {"isbn": ISBN})
    show("2) 제목으로 조회 (키 자체가 되는지 확인)", {"title": "창조적 습관"})
    show("3) 발행일 범위로 조회 (가장 느슨한 조건)",
         {"start_publish_date": "20260701", "end_publish_date": "20260731"})
    print(f"\n{'=' * 60}")
    print("판단 기준:")
    print("  · 전부 0건 + 오류 메시지 → 인증키 승인 대기 또는 키 오류")
    print("  · 3) 만 결과 있음        → ISBN 검색 방식 문제")
    print("  · 결과는 있는데 URL 칸이 비어 있음 → 자료 자체가 없는 것 (진짜 수록률 문제)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
