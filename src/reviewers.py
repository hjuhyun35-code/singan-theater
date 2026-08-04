"""초안이 만들어질 때마다 '인스타 독자' 입장에서 봐주는 사람들.

readers.json 에 적힌 사람들이 각각 따로 봅니다. 서로의 의견을 모르는 채로
반응하기 때문에, 다섯 명이 같은 곳을 지적하면 그건 진짜 문제입니다.

발행을 막지는 않습니다. 판단 재료만 드립니다.
"""

import json
from pathlib import Path

from anthropic import Anthropic

from .settings import ROOT, env

READERS_PATH = ROOT / "readers.json"

# 도구 속성 이름은 영문만 됩니다(API 제한). 화면에 보일 때만 한글로 바꿉니다.
TOOL = {
    "name": "reaction",
    "description": "인스타를 넘겨보다가 이 게시물을 만난 사람의 반응.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stopped": {
                "type": "boolean",
                "description": "첫 장을 보고 멈춰서 읽었는가. 그냥 넘겼으면 false.",
            },
            "saved": {
                "type": "boolean",
                "description": "나중에 보려고 저장할 것인가. ★stopped 가 false 면 여기도 반드시 false. 안 읽고 지나친 글을 저장할 수는 없다.",
            },
            "followed": {
                "type": "boolean",
                "description": "이 계정을 팔로우할 마음이 드는가. ★stopped 가 false 면 여기도 반드시 false.",
            },
            "comment": {
                "type": "string",
                "description": "속으로 든 생각 한 줄. 한국어로 30자 이내. 솔직하게. 좋게 포장하지 말 것.",
            },
            "issue": {
                "type": "string",
                "description": "가장 거슬린 것 하나. 한국어로 30자 이내. 없으면 빈 문자열.",
            },
        },
        "required": ["stopped", "saved", "followed", "comment", "issue"],
    },
}

SYSTEM = """너는 지금 인스타그램을 넘겨보다가 책 소개 게시물을 만난 한 사람이다.
평론가가 아니라 그냥 지나가던 사용자다.

- 예의를 차리지 마라. 재미없으면 재미없다고 하라.
- 만든 사람 기분을 생각하지 마라. 솔직한 반응이 도움이 된다.
- 좋으면 좋다고 해라. 억지로 흠을 잡을 필요도 없다.
- 너의 나이와 성향에 맞게 반응하라. 다른 사람이라면 다르게 볼 수도 있다."""


def load_readers() -> list[dict]:
    if not READERS_PATH.exists():
        return []
    return json.loads(READERS_PATH.read_text(encoding="utf-8")).get("독자", [])


def _post_as_text(book: dict, copy: dict) -> str:
    lines = [
        f"[책] {book['title']} / {book.get('author_display') or book.get('author','')}",
        "",
        "[인스타 카드 — 넘기면서 보는 순서]",
    ]
    for i, s in enumerate(copy.get("slides", []), 1):
        head = s.get("headline", "")
        body = " ".join((s.get("body") or "").split())
        kicker = s.get("kicker", "")
        lines.append(f"{i}장 {('['+kicker+'] ') if kicker else ''}{head}")
        if body:
            lines.append(f"    {body}")
    lines += ["", "[캡션 첫 줄]", copy.get("search_line", "")]
    return "\n".join(lines)


def review(book: dict, copy: dict, config: dict) -> list[dict]:
    """독자들의 반응을 모읍니다. 실패해도 초안 생성을 막지 않습니다."""
    readers = load_readers()
    if not readers or not config.get("독자평가", {}).get("사용", True):
        return []

    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model = config["모델"]["이름"]
    content = _post_as_text(book, copy)
    out: list[dict] = []

    for r in readers:
        who = (
            f"너는 {r['이름']}, {r['나이']}세.\n{r.get('한줄','')}\n{r.get('성향','')}"
        )
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=400,
                system=f"{SYSTEM}\n\n{who}",
                tools=[TOOL],
                tool_choice={"type": "tool", "name": "reaction"},
                messages=[
                    {
                        "role": "user",
                        "content": f"{content}\n\n이 게시물을 봤다. 어떻게 반응했나?",
                    }
                ],
            )
            got = next((b.input for b in msg.content if b.type == "tool_use"), None)
        except Exception as exc:  # 검수 실패로 초안을 날리지 않습니다
            print(f"    ! 독자 {r['이름']} 확인 실패: {exc}")
            continue
        if not got:
            continue
        stopped = bool(got.get("stopped"))
        out.append(
            {
                "이름": r["이름"],
                "나이": r["나이"],
                "행동": "멈춰서 읽음" if stopped else "넘김",
                # 안 읽고 지나친 사람이 저장·팔로우할 수는 없습니다.
                "저장": stopped and bool(got.get("saved")),
                "팔로우": stopped and bool(got.get("followed")),
                "한마디": (got.get("comment") or "").strip(),
                "걸린점": (got.get("issue") or "").strip(),
            }
        )

    return out


def summarize(reviews: list[dict]) -> dict:
    """숫자로 요약하고, 어디가 문제인지 한 줄로 짚어줍니다."""
    if not reviews:
        return {}
    n = len(reviews)
    stop = sum(1 for r in reviews if r.get("행동") == "멈춰서 읽음")
    save = sum(1 for r in reviews if r.get("저장"))
    follow = sum(1 for r in reviews if r.get("팔로우"))
    return {
        "인원": n,
        "멈춤": stop,
        "넘김": n - stop,
        "저장": save,
        "팔로우": follow,
        "진단": _diagnose(n, stop, save, follow),
    }


def _diagnose(n: int, stop: int, save: int, follow: int) -> str:
    """어디가 약한지 짚습니다. 후하게 봐주면 쓸모가 없어지므로 기준을 짭니다.

    멈춤 = 첫 장의 힘, 저장 = 내용의 힘, 팔로우 = 계정의 힘.
    """
    if stop == 0:
        return "아무도 멈추지 않았습니다. 첫 장을 다시 쓰는 게 좋습니다"
    if stop <= n // 3:
        return "대부분 그냥 넘겼습니다. 첫 장이 약합니다"
    if save == 0:
        return "읽기는 하는데 남길 게 없다고 봅니다. 마지막 장이 약합니다"
    if save >= n * 3 // 5 and follow >= n // 3:
        return "반응이 좋습니다"
    if follow == 0:
        return "저장은 해도 팔로우까지는 안 갑니다. 이 계정을 계속 볼 이유가 약합니다"
    return "나쁘지 않지만 특별하지도 않습니다"
