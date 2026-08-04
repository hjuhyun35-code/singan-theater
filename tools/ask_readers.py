"""독자들에게 직접 물어봅니다.

게시물 반응 말고, 방향을 정할 때 의견을 듣는 용도입니다.
readers.json 의 사람들이 각자 따로 답합니다.

  .venv\\Scripts\\python.exe tools\\ask_readers.py "질문" 보기1 보기2 보기3
  .venv\\Scripts\\python.exe tools\\ask_readers.py "질문"          # 보기 없이 자유 답변
"""

import sys
from collections import Counter
from pathlib import Path

from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.reviewers import SYSTEM, load_readers  # noqa: E402
from src.settings import env, load_config  # noqa: E402


def _clean(text: str) -> str:
    """모델이 가끔 태그를 섞어 보냅니다. 보기 좋게 걷어냅니다."""
    import re

    return re.sub(r"</?[a-zA-Z][^>]*>", " ", str(text)).replace("  ", " ").strip()


def build_tool(choices: list[str]) -> dict:
    props = {
        "answer": {
            "type": "string",
            "description": "고른 것 하나. 보기가 있으면 그중에서 고를 것.",
        },
        "why": {"type": "string", "description": "왜 그런지 한국어로 60자 이내."},
        "condition": {
            "type": "string",
            "description": "어떤 조건이면 팔로우까지 할 것인지 한국어로 50자 이내.",
        },
    }
    if choices:
        props["answer"]["enum"] = choices
    return {
        "name": "opinion",
        "description": "질문에 대한 솔직한 생각.",
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": ["answer", "why", "condition"],
        },
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    question = sys.argv[1]
    choices = sys.argv[2:]
    readers = load_readers()
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model = load_config()["모델"]["이름"]
    tool = build_tool(choices)

    print(f"질문: {question}")
    if choices:
        print(f"보기: {' / '.join(choices)}")
    print()

    picks = Counter()
    for r in readers:
        who = f"너는 {r['이름']}, {r['나이']}세.\n{r.get('한줄','')}\n{r.get('성향','')}"
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=400,
                system=f"{SYSTEM}\n\n{who}",
                tools=[tool],
                tool_choice={"type": "tool", "name": "opinion"},
                messages=[{"role": "user", "content": question}],
            )
            got = next((b.input for b in msg.content if b.type == "tool_use"), None)
        except Exception as exc:
            print(f"  ! {r['이름']} 실패: {exc}")
            continue
        if not got or not got.get("answer"):
            continue
        # 가끔 응답이 깨져 일부 항목이 빠집니다. 그것 때문에 전체가 멈추면 안 됩니다.
        answer = str(got["answer"]).strip()
        why = _clean(got.get("why", ""))
        cond = _clean(got.get("condition", ""))
        picks[answer] += 1
        print(f"■ {r['이름']}({r['나이']}) → {answer}")
        if why:
            print(f"   {why}")
        if cond:
            print(f"   팔로우 조건: {cond}")
        print()

    if picks:
        print("=" * 52)
        for name, n in picks.most_common():
            print(f"  {name:<12} {n}표")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
