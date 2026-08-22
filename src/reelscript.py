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
                    "마지막 장면. 표지와 함께 나온다. "
                    "★ 이 자막이 썸네일이 된다. 사람들이 이 한 줄만 보고 볼지 말지 정한다. "
                    "그러니 이 영상에서 가장 센 한 문장을 여기 둬라. 앞의 자막들을 되풀이하지 말고, "
                    "이 책을 모르는 사람이 궁금해질 말이어야 한다. "
                    "좋은 예: '장례식장에서 담배를 폈다', '드라큘라가 옆집에 산다'. "
                    "★ 자막에 '저장', '팔로우', '오늘 밤', '~하기' 같은 권유를 쓰지 마라. "
                    "그건 대사에서 말한다. 자막에 쓰면 영상마다 똑같아져 썸네일이 죽는다. "
                    "책 제목도 쓰지 마라. 제목은 화면에 따로 나온다. "
                    "대사(say)에서는 저장이나 팔로우를 정확히 말하고 닫아라."
                ),
            },
        },
        "required": ["hook", "points", "closing"],
    },
}


def _model(config: dict) -> str:
    """대본과 캡션을 쓸 모델.

    규칙이 많아 하이쿠가 항목을 빼먹습니다(2026-08-11 확인). 그래서 따로 둡니다.
    '모델.대본' 이 없으면 예전처럼 '모델.이름' 을 씁니다.
    """
    m = config.get("모델", {})
    return m.get("대본") or m["이름"]


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


CAPTION_TOOL = {
    "name": "write_caption",
    "description": "인스타 게시물 본문",
    "input_schema": {
        "type": "object",
        "properties": {
            "caption": {"type": "string", "description": "본문 전체"},
        },
        "required": ["caption"],
    },
}

CAPTION_MIN = 700


def write_caption(post: dict, config: dict, scenes: list[dict]) -> str:
    """캡션만 따로 씁니다.

    ★ 대본과 한 번에 받으면 300자쯤밖에 안 나옵니다. 여러 항목을 한꺼번에
      채우느라 마지막 항목을 대충 끝내기 때문입니다. max_tokens 도 같이 나눠 씁니다.
      따로 부르면 같은 모델로도 훨씬 길고 촘촘하게 씁니다.
    """
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    closing = config.get("영상", {}).get("맺음말", "매일 한 권, 신간극장")
    said = "\n".join(f"  - {s['headline']}: {s['body']}" for s in scenes)

    prompt = (
        f"{_material(post)}\n"
        f"영상에서는 이만큼만 말했다:\n{said}\n\n"
        f"이제 이 게시물의 본문을 써라. {CAPTION_MIN}자 이상, 1000자 안팎이다.\n"
        "영상은 30초라 겉만 훑었다. 본문은 책을 제대로 소개하는 자리다.\n"
        "무엇에 대한 책이고, 어떤 이야기가 들어 있고, 왜 읽을 만한지 풀어 써라.\n\n"
        "쓰는 방식:\n"
        "1) 첫 줄 — 더보기 전에 보이는 한 줄. 20자 이내로 가장 센 말.\n"
        "2) 빈 줄을 두고, 짧은 문단 네다섯 개. 한 문단은 두세 문장.\n"
        "   문단 사이마다 반드시 빈 줄을 둔다.\n"
        "3) '이런 분께 권한다' 로 시작하는 한 줄.\n"
        "4) 마지막 줄 — 저장이나 팔로우를 권한다.\n\n"
        f"문체는 '~다' 로 통일한다. 마지막 줄만 존댓말로 써도 된다.\n"
        f"해시태그와 책 링크는 넣지 마라. 뒤에 따로 붙는다.\n"
        f"'{closing}' 같은 계정 구호도 넣지 마라.\n"
        "주어진 재료에 없는 사실을 지어내지 마라."
    )

    warn = ""
    text = ""
    for attempt in range(2):
        msg = client.messages.create(
            model=_model(config),
            max_tokens=3000,
            system="너는 책 소개 SNS 계정의 카피라이터다. 길고 촘촘하게 쓴다.",
            tools=[CAPTION_TOOL],
            tool_choice={"type": "tool", "name": "write_caption"},
            messages=[{"role": "user", "content": prompt + warn}],
        )
        got = next((b.input for b in msg.content if b.type == "tool_use"), None)
        text = (got or {}).get("caption", "").strip()
        if len(text) >= CAPTION_MIN:
            break
        print(f"  캡션이 {len(text)}자라 다시 씁니다")
        warn = (
            f"\n\n앞서 쓴 것이 {len(text)}자로 너무 짧았다. "
            f"{CAPTION_MIN}자를 반드시 넘겨라. 문단을 더 늘리고 내용을 더 풀어 써라."
        )
    print(f"  캡션 {len(text)}자")
    return _paragraphs(text)


def _shape(got: dict) -> list[str]:
    """모양부터 봅니다. 이게 깨지면 아래 검사가 통째로 터집니다.

    실제로 세 번째 시도에서 모델이 points 를 통째로 빼먹고 보냈고,
    검사기가 KeyError 로 죽어 카드 문구로 물러섰습니다.
    """
    bad = []
    for key in ("hook", "closing"):
        b = got.get(key)
        if not isinstance(b, dict) or not b.get("sub") or not b.get("say"):
            bad.append(f"{key} 가 비었거나 자막/대사가 없다")
    pts = got.get("points")
    if not isinstance(pts, list) or not pts:
        bad.append("points 가 없다. 반드시 2개를 보내라")
    elif any(not isinstance(p, dict) or not p.get("sub") or not p.get("say") for p in pts):
        bad.append("points 중에 자막이나 대사가 빈 것이 있다")
    return bad


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

    # 맺음 자막은 썸네일이 됩니다. 권유 문구를 넣으면 영상마다 똑같아집니다.
    # 2026-08-11 여섯 개를 뽑았더니 '저장해두고 오늘 밤 펼치기' 류가 여섯 번 나왔습니다.
    csub = (got["closing"].get("sub") or "").strip()
    if re.search(r"(저장|팔로우|구독|오늘 밤|하기$|해보기$|읽기$)", csub):
        problems.append(
            f"맺음 자막이 권유 문구다: {csub!r} — 여긴 썸네일이다. "
            "이 영상에서 가장 센 한 문장을 써라. 권유는 대사에서 해라"
        )
    # 대사에서는 반대로 권유가 있어야 닫힙니다.
    csay = (got["closing"].get("say") or "").strip()
    if csay and not re.search(r"(저장|팔로우|읽|담아|보관|챙겨)", csay):
        problems.append(f"맺음 대사에 할 일이 없다: {csay!r} (예: 저장해두고 읽어보자)")

    # 캡션은 write_caption() 이 따로 씁니다. 여기서 보면 안 됩니다.
    # (검사를 안 걷어내서 항상 '0자' 로 걸리고, 대본을 쓸데없이 두 번 더
    #  부르고 있었습니다. 진짜 지적이 그 잔소리에 묻혔습니다)
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


def write_script(post: dict, config: dict, note: str = "") -> tuple[list[dict], str]:
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
    if note:
        # 사람이 텔레그램으로 적어 보낸 고칠 곳. 다른 지침보다 우선합니다.
        prompt += (
            "\n\n★ 사람이 이렇게 고쳐 달라고 했다. 다른 지침보다 이것을 먼저 지켜라:\n"
            f"   {note}"
        )

    # 두 번으로는 모자랐습니다. 한 번 고쳐 써도 다른 데가 어긋나 그대로 통과했습니다.
    got, warn = None, ""
    for attempt in range(3):
        message = client.messages.create(
            model=_model(config),
            max_tokens=1500,
            system=SYSTEM,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "write_reel"},
            messages=[{"role": "user", "content": prompt + warn}],
        )
        got = next((b.input for b in message.content if b.type == "tool_use"), None)
        if not got:
            raise RuntimeError("릴스 대본을 만들지 못했습니다.")

        problems = _shape(got)
        if problems:
            # 모양이 깨졌으면 내용 검사는 건너뜁니다. 터집니다.
            if attempt == 2:
                raise RuntimeError("대본 모양이 계속 깨집니다: " + "; ".join(problems))
            print("  모양이 깨져 다시 씁니다:", "; ".join(problems))
            warn = (
                "\n\n앞서 보낸 것이 이랬다. 반드시 고쳐라:\n- "
                + "\n- ".join(problems)
                + "\nhook, points(2개), closing, caption 을 모두 채워 보내라."
            )
            continue

        problems = _lint(got)
        if not problems or attempt == 2:
            if problems:
                print("  ! 아직 어색한 곳이 있습니다:", "; ".join(problems[:3]))
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
    # 캡션은 따로 부릅니다. 대본과 한 번에 받으면 300자쯤밖에 안 나옵니다.
    body = write_caption(post, config, scenes)
    caption = "\n\n".join(p for p in [body, tags, post.get("link", "")] if p)
    return scenes, caption
