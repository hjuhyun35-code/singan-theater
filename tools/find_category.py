"""알라딘 분야(카테고리) ID를 찾아줍니다.

config.json 의 '카테고리ID' 를 바꾸고 싶을 때 씁니다.
어떤 분야의 신간이 실제로 어떻게 잡히는지 눈으로 확인할 수 있습니다.

사용법:
  .venv\\Scripts\\python.exe tools\\find_category.py            # 자주 쓰는 분야 목록
  .venv\\Scripts\\python.exe tools\\find_category.py 336        # 그 분야 신간 미리보기
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.aladin import fetch_list, normalize  # noqa: E402

COMMON = [
    (0, "전체"),
    (1, "소설/시/희곡"),
    (170, "경제경영"),
    (336, "자기계발"),
    (656, "인문학"),
    (798, "사회과학"),
    (74, "역사"),
    (987, "과학"),
    (55889, "에세이"),
    (351, "컴퓨터/모바일"),
    (2551, "만화"),
    (1230, "건강/취미"),
    (517, "가정/살림"),
    (1196, "여행"),
    (2913, "고전"),
]


def main() -> int:
    if len(sys.argv) == 1:
        print("자주 쓰는 분야 ID (config.json 의 카테고리ID 에 넣으세요)\n")
        for cid, name in COMMON:
            print(f"  {cid:>7}  {name}")
        print("\n특정 분야의 신간을 미리 보려면:")
        print("  .venv\\Scripts\\python.exe tools\\find_category.py 336")
        print("\n더 세분화된 ID는 알라딘이 배포하는 카테고리 목록 파일에서 찾을 수 있습니다:")
        print("  https://www.aladin.co.kr/ttb/wblog_manage.aspx 의 '카테고리 목록' 다운로드")
        return 0

    cid = int(sys.argv[1])
    items = fetch_list("ItemNewSpecial", cid, max_results=10)
    if not items:
        print(f"카테고리 {cid} 에서 신간을 찾지 못했습니다. ID가 맞는지 확인하세요.")
        return 1

    print(f"카테고리 {cid} 의 주목할 만한 신간 {len(items)}권\n")
    for i, raw in enumerate(items, 1):
        b = normalize(raw)
        print(f"{i:>2}. {b['title']}")
        print(f"    {b['author']} | {b['publisher']} | {b['pub_date']}")
        print(f"    분야: {b['category']}")
        print(f"    소개글 길이: {len(b['description'])}자")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
