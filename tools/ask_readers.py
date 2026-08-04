"""독자들에게 직접 물어봅니다.

게시물 반응 말고, 방향을 정할 때 의견을 듣는 용도입니다.
readers.json 의 사람들이 각자 따로 답합니다.

  .venv\\Scripts\\python.exe tools\\ask_readers.py "질문" 보기1 보기2 보기3
  .venv\\Scripts\\python.exe tools\\ask_readers.py "질문"          # 보기 없이 자유 답변

이미지를 같이 보여주려면 --img 로 파일을 붙입니다. 보기 순서와 같은 순서로 넣으세요.
  ... "질문" 밤 아이보리 --img out/밤.jpg --img out/아이보리.jpg
"""

import base64
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


def image_block(path: Path) -> dict:
    """이미지를 모델이 볼 수 있는 형태로 감쌉니다."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        },
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    args = sys.argv[1:]
    images: list[Path] = []
    while "--img" in args:
        i = args.index("--img")
        images.append(Path(args[i + 1]))
        del args[i : i + 2]

    question = args[0]
    choices = args[1:]
    readers = load_readers()
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model = load_config()["모델"]["이름"]
    tool = build_tool(choices)

    print(f"질문: {question}")
    if choices:
        print(f"보기: {' / '.join(choices)}")
    if images:
        print(f"보여줄 그림 {len(images)}장: {', '.join(p.name for p in images)}")
    print()

    # 그림을 먼저 보여주고, 어느 게 어느 보기인지 이름을 붙여줍니다.
    content: list[dict] = []
    for i, path in enumerate(images):
        label = choices[i] if i < len(choices) else path.stem
        content.append({"type": "text", "text": f"[{label}]"})
        content.append(image_block(path))
    content.append({"type": "text", "text": question})

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
                messages=[{"role": "user", "content": content}],
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
