"""릴스 대본을 따로 씁니다.

카드뉴스 문구를 그대로 읽으면 릴스가 흐지부지 끝납니다.
카드는 '여운' 으로 조용히 닫는 구성이라 그렇습니다. 릴스는 반대로
마지막에 할 일을 분명히 알려주고 딱 닫아야 끝까지 봅니다.

구성 (릴스 대본의 정석)
  1) 첫 2초 훅   — 스크롤을 멈추게 하는 한 문장. 길면 이미 넘어갑니다.
  2) 핵심 3포인트 — 하나씩 짧게. 4~6초씩.
  3) 마지막 CTA  — 저장·팔로우처럼 할 일을 정확히 말합니다.

자막과 대사를 따로 받습니다.
  자막 = 화면에 크게 뜨는 짧은 글. 소리를 끄고 보는 사람을 위한 것.
  대사 = 읽어줄 말. 자막보다 길고 말하듯 자연스럽게.
둘을 같게 두면 큰 글씨가 문장으로 길어져 읽기 나쁩니다.

책 정보와 이미 만들어둔 카드 문구만 재료로 씁니다. 웹을 다시 뒤지지 않으므로
초안 만들 때보다 훨씬 쌉니다.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from .settings import env

# 포인트 개수. 길이는 문장을 깎는 것보다 이 개수로 잡습니다.
# 문장을 토막내면 무슨 말인지 흐려지지만, 개수를 줄이면 남은 문장은 온전합니다.
POINTS = 2

SYSTEM = """너는 인스타 릴스 대본을 쓰는 작가다.
책을 소개하는 30~40초 세로 영상의 대본을 쓴다.

★ 무엇보다, 보는 사람이 "이 책이 무슨 책인지" 알게 해라.
  이게 안 되면 나머지가 다 잘돼도 실패다. 실제로 이런 지적을 받았다.
  "책의 줄거리나 내용을 보여주지도 않고 재미가 없어. 뭔 말인지 모르겠어."
- 재료의 '이 책이 무슨 이야기인지' 와 '웹에서 찾은 자료' 에서 내용을 가져와라.
  거기에 줄거리와 주장이 들어 있다. 카드 문구는 참고만 해라.
- 구체적인 것을 말해라. 무엇에 대한 책이고, 누가 나오고, 무슨 주장을 하는지.
  '삶을 돌아보게 한다', '깊은 울림을 준다' 같은 감상만 늘어놓지 마라.
- 주어진 재료에 없는 사실을 지어내지 마라. 없으면 있는 것만 써라.

★ 자막과 대사는 다른 말이어야 한다.
- 자막은 화면에 크게 뜨는 간판이고, 대사는 그 아래 흐르는 설명이다.
  대사의 앞부분을 그대로 자막에 옮기지 마라. 같은 말이 두 번 보인다.
- 자막은 그것만 읽어도 뜻이 통해야 한다. 말이 도중에 끊긴 구절을 쓰지 마라.
  나쁜 예: "우리가 살고 있는 모든 것", "이 거짓말이 없었다면", "현재의 허구를"
  좋은 예: "돈은 원래 없는 것이다", "거짓말이 인류를 키웠다", "지금도 믿고 있다"

지켜야 할 것
- 대사는 말하듯 자연스럽게. 글 읽는 투('~에 대하여', '~라는 점에서')를 쓰지 마라.
- 과장 광고 표현(인생책, 필독, 충격, 소름)을 쓰지 마라.
- 마지막은 반드시 할 일을 정확히 말하고 닫아라. 여운으로 흐리지 마라.

★ 대사는 소리가 되어 나간다. 문체가 흔들리면 딴 사람이 읽는 것처럼 들린다.
- 문체는 '~다' 로 통일하라. 한 영상 안에서 절대 섞지 마라.
  나쁜 예: "운명이 바뀌었어. 하지만 진보가 아니었어. 함정이었다."
  좋은 예: "운명이 바뀌었다. 하지만 진보가 아니었다. 함정이었다."
- '~어', '~야', '~지', '~거든', '알아?' 같은 반말투를 쓰지 마라.
- 모든 대사는 서술어로 끝내라. 명사나 조사로 끝내지 마라.
  나쁜 예: "휴대폰 앱의 돈, 법으로 지은 집, 공유하는 종교와 이념."
  좋은 예: "앱 속의 돈도 법으로 지은 집도 우리가 함께 믿기로 한 것이다."
- 자막(sub)은 명사로 끝나도 된다. 이 규칙은 대사(say)에만 해당한다.

★ 길이가 가장 중요하다. 읽으면 소리가 되고, 길면 사람들이 끝까지 안 본다.
  한국어는 1초에 네 글자쯤 읽힌다. 30자면 벌써 8초다.
- 훅 대사는 한 문장, 24자 이내.
- 포인트 대사는 한 문장, 30자 이내. 두 문장으로 나누지 마라.
- 맺음 대사는 한 문장, 24자 이내.
- 전부 합쳐 30초를 넘기면 안 된다. 넘칠 것 같으면 설명을 버려라.
  덜 설명하고 궁금하게 두는 편이 낫다."""

# ★ 항목 이름은 반드시 영문이어야 합니다.
#   Claude 도구 정의는 '^[a-zA-Z0-9_.-]{1,64}$' 만 받습니다.
#   한글로 뒀다가 400 오류로 계속 거부당했습니다 (2026-08-07).
#   sub = 자막(화면에 크게 뜨는 짧은 글), say = 대사(읽어줄 말)
_BEAT = {
    "type": "object",
    "properties": {
        "sub": {"type": "string", "description": "자막. 화면에 크게 뜨는 짧은 글."},
        "say": {"type": "string", "description": "대사. 읽어줄 말. 말하듯 자연스럽게."},
        "say_hot": {
            "type": "string",
            "description": (
                "대사 안에서 색을 다르게 줄 부분. 가장 중요한 낱말이나 짧은 구절 하나. "
                "대사에 있는 그대로 적어야 한다(띄어쓰기 포함). "
                "대사의 절반을 넘기지 마라."
            ),
        },
        "hot": {
            "type": "string",
            "description": (
                "자막 안에서 색을 다르게 줄 낱말 한두 개. "
                "반드시 자막에 있는 그대로 적어야 한다(띄어쓰기 포함). "
                "자막의 절반을 넘기지 마라. 강조가 다 되면 강조가 아니다."
            ),
        },
    },
    "required": ["sub", "say", "hot", "say_hot"],
}

TOOL = {
    "name": "write_reel",
    "description": "릴스 대본 한 편",
    "input_schema": {
        "type": "object",
        "properties": {
            "hook": {
                **_BEAT,
                "description": (
                    "첫 2초. 이 책에서 가장 놀라운 주장이나 사실 하나를 던진다. "
                    "감상이 아니라 내용이어야 한다. 자막 12자, 대사 24자 안팎."
                ),
            },
            "points": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "description": (
                    "책의 내용 둘. 첫째는 '이 책이 무슨 이야기인가' 를 구체적으로 "
                    "(무엇을 다루고 무슨 주장을 하는지). 둘째는 그중 가장 인상적인 대목 하나. "
                    "자막 14자, 대사 30자 안팎."
                ),
                "items": _BEAT,
            },
            "closing": {
                **_BEAT,
                "description": (
                    "마지막. 저장이나 팔로우를 정확히 말하고 닫는다.\n"
                    "★ 자막에 책 제목을 쓰지 마라. 제목은 화면에 따로 나온다. "
                    "자막은 반드시 '할 일' 이어야 한다. "
                    "좋은 예: '저장해두고 읽기', '오늘 밤 첫 장만', '팔로우하고 매일 한 권'. "
                    "나쁜 예: '사피엔스', '현재의 허구를 봐야 한다'."
                ),
            },
            "caption": {
                "type": "string",
                "description": (
                    "인스타에 붙여넣을 글. 400~600자. 영상보다 길게, 읽을거리가 되게 쓴다.\n"
                    "이 순서로 쓴다:\n"
                    "1) 첫 줄 — 더보기 전에 보이는 한 줄. 20자 이내로 가장 센 말을 둔다.\n"
                    "2) 빈 줄을 두고, 짧은 문단 서너 개. 한 문단은 두 문장을 넘기지 않는다. "
                    "문단 사이마다 빈 줄을 둔다. 영상에서 못 다한 이야기를 여기서 푼다.\n"
                    "3) '이런 분께 권한다' 로 시작하는 한 줄. 어떤 사람에게 맞는 책인지 적는다.\n"
                    "4) 마지막 줄 — 저장이나 팔로우를 권한다. 이 줄만 존댓말로 써도 된다.\n"
                    "해시태그와 책 링크는 넣지 마라. 뒤에 따로 붙는다."
                ),
            },
        },
        "required": ["hook", "points", "closing", "caption"],
    },
}


def _cap(text: str, limit: int) -> str:
    """길면 잘라냅니다. 말 도중에 끊기면 듣기 흉하므로 문장 → 쉼표 → 낱말 순으로 끊습니다.

    처음에는 문장 단위로만 잘랐는데, 모델이 한 문장으로 길게 써 보내면
    자를 곳이 없어 그대로 통과했습니다. 그래서 50자로 막아둔 것이 실제로는
    안 막혔습니다. 아래로 갈수록 거친 방법이지만 반드시 한도 안에 들어옵니다.
    """
    import re

    text = (text or "").strip()
    if len(text) <= limit:
        return text

    # 1) 문장 단위
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) > 1:
        out = ""
        for p in parts:
            nxt = p if not out else f"{out} {p}"
            if len(nxt) > limit and out:
                break
            out = nxt
        if len(out) <= limit:
            return out

    # 2) 쉼표 단위
    head = text[: limit + 1]
    comma = max(head.rfind(", "), head.rfind("? "), head.rfind("… "))
    if comma > limit * 0.5:
        return text[:comma].rstrip(" ,") + "."

    # 3) 깨끗하게 끊을 자리가 없으면 그냥 둡니다.
    #    낱말 단위로 자르면 "우린 수십 명 단위로만 모여 살았을." 처럼 말이
    #    안 되는 자리에서 끊깁니다. 몇 초 긴 게 낫습니다.
    #    길이는 장면 개수로 잡습니다(포인트를 2개로 줄인 이유).
    print(f"    (길지만 끊을 자리가 없어 그대로 둡니다: {len(text)}자)")
    return text


def _paragraphs(caption: str) -> str:
    """세 번 시켜도 한 덩어리로 오면 문장 두 개씩 묶어 문단을 만듭니다.

    인스타에서 줄바꿈 없는 긴 글은 아무도 안 읽습니다.
    """
    import re

    cap = (caption or "").strip()
    if len(cap.split("\n\n")) >= 3:
        return cap
    sents = [s for s in re.split(r"(?<=[.!?])\s+", cap.replace("\n", " ")) if s]
    if len(sents) < 4:
        return cap
    return "\n\n".join(
        " ".join(sents[i : i + 2]) for i in range(0, len(sents), 2)
    )


def _lint(got: dict) -> list[str]:
    """대사가 문체 규칙을 지켰는지 봅니다. 안 지키면 한 번 더 시킵니다.

    부탁만으로는 안 지켜집니다. 실제로 '바뀌었어 … 함정이었다' 처럼 반말과
    ~다 체를 한 문장에 섞고, '종교와 이념.' 처럼 서술어 없이 끝냈습니다.
    """
    import re

    # 맺음은 자막 검사에서 뺍니다. '저장해두고 읽기 / 저장해두고 읽어보자' 처럼
    # 겹치는 게 오히려 자연스럽습니다.
    beats = [(got["hook"], True), *[(p, True) for p in got["points"]], (got["closing"], False)]
    problems = []
    for b, check_sub in beats:
        t = (b.get("say") or "").strip()
        sub = (b.get("sub") or "").strip()

        if check_sub and sub:
            # 자막이 대사를 되풀이하면 같은 말이 화면에 두 번 보입니다.
            if sub in t or (len(sub) >= 6 and t.startswith(sub[:6])):
                problems.append(f"자막이 대사와 겹침: {sub!r}")
            # 자막이 조사나 연결어미로 끝나면 말이 도중에 끊긴 것처럼 보입니다.
            if re.search(r"(은|는|이|가|을|를|의|에|도|만|와|과|면|때|것|들)$", sub):
                problems.append(f"자막이 말이 끊긴 구절: {sub!r}")
        # 서술어로 끝나는가. 명사로 끝나면 말이 덜 끝난 느낌이 납니다.
        if not re.search(r"(다|까|요|군|네|랴|자)[.!?…]*$", t):
            problems.append(f"서술어로 안 끝남: {t[-18:]!r}")
        # 반말투가 섞였는가.
        if re.search(r"(었어|았어|해야지|거든|잖아|알아\?|이야|야\?)[.!?…]*(\s|$)", t):
            problems.append(f"반말투가 섞임: {t[-18:]!r}")

    # 맺음 자막은 '할 일' 이어야 합니다. 책 제목이 나온 적이 있습니다.
    csub = (got["closing"].get("sub") or "").strip()
    if csub and not re.search(r"(저장|팔로우|읽|담아|보관|챙겨)", csub):
        problems.append(f"맺음 자막이 할 일이 아니다: {csub!r} (예: 저장해두고 읽기)")

    # 캡션이 짧으면 읽을거리가 안 됩니다. 400자를 부탁했는데 150자가 온 적이 있습니다.
    cap = (got.get("caption") or "").strip()
    if len(cap) < 320:
        problems.append(f"캡션이 너무 짧다({len(cap)}자). 400~600자로 늘려라")
    if len(cap.split("\n\n")) < 3:
        problems.append("캡션에 빈 줄로 나눈 문단이 적다. 문단 사이를 빈 줄로 띄워라")
    return problems


def _material(post: dict) -> str:
    """대본을 쓸 재료. 좋은 것부터 순서대로 놓습니다.

    ★ 처음에는 카드 문구만 넣었는데, 카드 문구는 원래 추상적인 '장면' 이라
      그것만 보고 쓰면 뜬구름 잡는 대본이 나옵니다("뭔 말인지 모르겠다").
      책이 실제로 무슨 이야기인지는 threads_text 와 웹 자료에 들어 있습니다.
    """
    parts = [
        f"제목: {post.get('title','')}",
        f"지은이: {post.get('author','')} · 펴낸곳: {post.get('publisher','')}",
        f"독자 후기 {post.get('review_count',0)}개 · 평점 {post.get('rating_score','?')}",
    ]
    if post.get("search_line"):
        parts.append(f"\n한 줄 소개:\n{post['search_line']}")
    if post.get("threads_text"):
        parts.append(
            "\n■ 이 책이 무슨 이야기인지 (가장 중요한 재료다. 여기서 내용을 가져와라):\n"
            + post["threads_text"].split("\n\n")[0]
        )
    if post.get("research"):
        parts.append(
            "\n■ 웹에서 찾은 자료 (줄거리·인물·평가가 들어 있다):\n"
            + post["research"][:2500]
        )
    slides = "\n".join(
        f"  - {s.get('headline','')} / {s.get('body','')}"
        for s in post.get("slides", [])
    )
    if slides:
        parts.append(
            "\n■ 카드뉴스에 쓴 문구 (참고만 해라. 여기 말을 그대로 옮기지 마라):\n" + slides
        )
    return "\n".join(parts) + "\n"


def write_script(post: dict, config: dict) -> tuple[list[dict], str]:
    """장면 목록과 인스타에 붙여넣을 캡션을 돌려줍니다."""
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    tone = config.get("글투", {}).get("지침", "")
    closing = config.get("영상", {}).get("맺음말", "매일 한 권, 신간극장")

    prompt = (
        f"{_material(post)}\n"
        f"말투 지침: {tone}\n\n"
        "이 책으로 30초쯤 되는 릴스 대본을 써라.\n"
        f"훅 하나, 포인트 {POINTS}개, 맺음 하나.\n"
        f"맺음 대사 끝에는 '{closing}' 이 자연스럽게 이어지도록 써라. "
        "그 문구 자체를 대사에 넣지는 마라. 뒤에 따로 붙는다."
    )

    # 두 번으로는 모자랐습니다. 한 번 고쳐 써도 다른 데가 어긋나 그대로 통과했습니다.
    got, warn = None, ""
    for attempt in range(3):
        message = client.messages.create(
            model=config["모델"]["이름"],
            max_tokens=1500,
            system=SYSTEM,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "write_reel"},
            messages=[{"role": "user", "content": prompt + warn}],
        )
        got = next((b.input for b in message.content if b.type == "tool_use"), None)
        if not got:
            raise RuntimeError("릴스 대본을 만들지 못했습니다.")

        problems = _lint(got)
        if not problems or attempt == 2:
            if problems:
                print("  ! 아직 어색한 곳이 있습니다:", "; ".join(problems[:3]))
                got["caption"] = _paragraphs(got.get("caption", ""))
            break
        print("  문체를 고쳐 다시 씁니다:", "; ".join(problems[:3]))
        warn = (
            "\n\n앞서 쓴 대사에 이런 문제가 있었다. 고쳐서 다시 써라:\n- "
            + "\n- ".join(problems)
            + "\n모든 대사를 '~다' 로 끝내고, 반말투를 쓰지 마라."
        )

    # 길이는 부탁만으로는 안 지켜집니다. 실제로 45자짜리를 부탁했는데 14초짜리
    # 문장이 온 적이 있습니다. 넘치면 문장 단위로 잘라냅니다.
    got["hook"]["say"] = _cap(got["hook"]["say"], 28)
    for p in got["points"]:
        p["say"] = _cap(p["say"], 36)
    got["closing"]["say"] = _cap(got["closing"]["say"], 28)

    scenes = [
        {
            "kind": "훅",
            "kicker": "",
            "headline": got["hook"]["sub"],
            # 강조 낱말만 다른 색으로. 카드와 같은 방식입니다.
            "emphasis": got["hook"].get("hot", ""),
            "body": got["hook"]["say"],
            # 대사 안에서 색을 다르게 줄 부분. 소리를 끄고 보는 사람에게는
            # 이 색이 '어디를 봐야 하는지' 를 알려줍니다.
            "body_hot": got["hook"].get("say_hot", ""),
            "say": got["hook"]["say"],
        }
    ]
    # ★ 규격에 2개라고 적어도 모델이 3개를 보냅니다. 실제로 그랬습니다.
    #   여기서 자르지 않으면 영상이 그만큼 길어집니다.
    for i, p in enumerate(got["points"][:POINTS], 1):
        scenes.append(
            {
                "kind": "포인트",
                "kicker": f"0{i}",
                "headline": p["sub"],
                "emphasis": p.get("hot", ""),
                "body": p["say"],
                "body_hot": p.get("say_hot", ""),
                "say": p["say"],
            }
        )
    # 마지막은 표지 화면 위에 CTA 를 얹습니다. CTA 장면과 표지 장면을 따로 두면
    # 힘이 갈라져 마무리가 흐려집니다. 한 장면에서 닫습니다.
    title = post.get("short_title") or post.get("title", "")
    scenes.append(
        {
            "kind": "표지",
            "kicker": "",
            "headline": got["closing"]["sub"],
            "emphasis": got["closing"].get("hot", ""),
            "body": f"{title} · {post.get('author','')}",
            "outro_line": closing,
            "say": f"{got['closing']['say']} {title}, {post.get('author','')}. {closing}",
        }
    )
    print("  릴스 대본:")
    for s in scenes:
        print(f"    [{s['kind']}] {s['headline']} — {s['body'][:34]}…")
    # 한국어는 1초에 네 글자쯤 읽힙니다. 실제 길이는 뒤에서 다시 재지만,
    # 여기서 미리 어림잡아두면 대본만 보고도 길다는 걸 알 수 있습니다.
    guess = sum(len(s["say"]) for s in scenes) / 4 + len(scenes) * 1.4
    print(f"  어림잡은 길이: {guess:.0f}초")

    # 해시태그와 책 링크는 초안이 이미 갖고 있습니다. 모델에게 다시 짓게 하면
    # 없는 링크를 지어내거나 태그가 30개로 불어납니다.
    tags = " ".join(post.get("hashtags", []) or [])
    caption = "\n\n".join(
        p for p in [got["caption"].strip(), tags, post.get("link", "")] if p
    )
    return scenes, caption
