"""Claude에게 책 소개 글감을 주고, 우리 계정 문구로 다시 쓰게 합니다.

핵심 원칙: 출판사 소개글을 '옮기지' 않고 '다시 쓴다'.
그대로 베낀 문장이 섞이면 저작권 문제가 되므로, 생성 후 원문과 겹치는
긴 문장이 있는지 기계적으로 검사합니다.
"""

import re

from anthropic import Anthropic

from .settings import env

MAX_THREADS_CHARS = 480  # Threads 한도 500자, 여유 확보
COPY_OVERLAP_LIMIT = 22  # 원문과 이만큼 연속으로 같으면 '베낌'으로 봅니다
THIN_SOURCE = 250        # 소개글이 이보다 짧으면 무슨 수를 써도 얕게 나옵니다

# 카드 종류별 작성 규칙. config.json 의 '카드구성 → 순서' 에서 골라 씁니다.
SLIDE_TYPES = {
    "훅": (
        "표지와 함께 나가는 첫 장. 이 책이 건드리는 문제를 한 문장으로 던져라. "
        "질문형도 좋다. kicker 는 '신간' 또는 분야 이름."
    ),
    "상황": (
        "독자가 겪어봤을 법한 구체적인 일상 장면 하나를 보여줘라. 설명하지 말고 장면으로 써라. "
        "'~할 때가 있다', '~한 적 있을 것이다' 처럼 독자 쪽으로 건네는 말투. "
        "★반드시 네가 지어낸 일반적인 상황이어야 하며, 책에 나오는 사례인 것처럼 쓰면 절대 안 된다. "
        "'책에 따르면', '저자는 ~한 사례를 든다' 같은 표현 금지. "
        "kicker 는 '이런 적 있다면' 또는 '혹시'."
    ),
    "이야기": (
        "이야기의 한 장면. body 를 2~4개의 짧은 문장으로 쓰고, 한 줄은 28자 안쪽으로 끊어라. "
        "설명하지 말고 눈에 보이게 써라. "
        "이 카드가 한 장뿐이라면 그 안에서 결말까지 내라. 시작만 하고 끝내지 마라. "
        "★주인공을 특정하지 마라. '한 사람은', '누군가는', '당신이라면' 으로 써라. "
        "'나는' 으로 쓰면 계정 주인이 실제로 겪은 일처럼 읽히므로 금지. "
        "★책에 실린 일화로 쓰면 절대 안 된다. 네가 만든 예시임이 분명해야 한다. "
        "kicker 는 '이런 이야기' 또는 '가령'."
    ),
    "핵심": (
        "이 책이 실제로 주장하는 바를 한 문장으로 압축하라. "
        "소개글과 목차에 근거가 있어야 한다. 근거가 없으면 지어내지 말고 범위를 좁혀라. "
        "논문 요약처럼 쓰지 말고, 친구에게 '결국 이런 얘기야' 하고 말해주듯 써라. "
        "앞에 이야기 카드가 있었다면, 그 이야기가 왜 그렇게 끝났는지를 여기서 짚어줘라. "
        "이야기와 무관한 일반론을 늘어놓지 마라. "
        "kicker 는 '결국' 또는 '이 책의 주장'."
    ),
    "질문": (
        "이 책이 답해주는 것 2~3개를 목차에서 뽑아 body 에 줄바꿈으로 나열하라. "
        "★시험문제나 목차처럼 딱딱하게 쓰지 마라. 사람이 속으로 하는 말투로 바꿔라. "
        "  나쁜 예: '운과 실력을 어떻게 구분하는가' "
        "  좋은 예: '이게 내 실력인지 그냥 운이 좋았던 건지 모르겠을 때' "
        "'~는가', '~에 대하여' 같은 어미를 쓰지 마라. "
        "headline 은 '이런 게 궁금했다면' 처럼 말 걸듯. kicker 는 '목차에서'."
    ),
    "정리": (
        "어떤 상황에 놓인 사람에게 이 책이 쓸모 있는지 한 문장으로 짚어라. "
        "'~라면' 으로 조건을 걸어라. 권하는 말투이되 강요하지 마라. "
        "kicker 는 '이런 사람에게'."
    ),
}

# 카드들이 서로 어떤 관계인지. config.json 의 '카드구성 → 흐름'.
FLOW_RULES = {
    "이어지기": (
        "★가장 중요한 규칙 — 이 카드 묶음 전체가 한 편의 글이다.\n"
        "  카드마다 따로 노는 요약 상자를 만들지 마라.\n"
        "  - 앞 카드에서 한 말을 뒤에서 되풀이하지 마라. 계속 앞으로 나아가라.\n"
        "  - 각 카드는 다음 장이 궁금해지는 지점에서 끊어라. 한 장 안에서 다 끝내지 마라.\n"
        "  - 뒷장은 앞장을 읽었다고 치고 이어 써라. 매번 처음부터 설명하지 마라.\n"
        "  - 마지막 장을 덮었을 때 하나의 이야기를 읽은 느낌이어야 한다."
    ),
    "묶음": (
        "카드는 각각 따로 읽혀도 되게 써라. 한 장만 캡처해도 뜻이 통해야 한다."
    ),
}

TOOL = {
    "name": "write_post",
    "description": "책 한 권에 대한 SNS 게시물 문구를 작성한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "threads_text": {
                "type": "string",
                "description": (
                    f"쓰레드에 올릴 본문. 해시태그 제외 {MAX_THREADS_CHARS}자 이내. "
                    "카드와 같은 이야기로 써라. 앞 두세 줄에서 장면을 보여주고, "
                    "마지막 한 줄에서 이 책이 무슨 얘기를 하는 책인지 닫아라. "
                    "'이 책은 ~을 다룬다' 같은 소개문으로 시작하지 마라."
                ),
            },
            "slides": {
                "type": "array",
                "description": "인스타 카드 각 장의 내용. 지정된 종류와 순서를 그대로 지켜야 한다.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": list(SLIDE_TYPES),
                            "description": "이 카드의 종류. 지시된 순서대로 채워라.",
                        },
                        "kicker": {"type": "string", "description": "카드 상단의 짧은 라벨. 8자 이내."},
                        "headline": {"type": "string", "description": "카드의 큰 글씨. 28자 이내."},
                        "body": {
                            "type": "string",
                            "description": "카드의 본문. 90자 이내. 단 '이야기' 카드는 150자까지 쓸 수 있다. 없으면 빈 문자열.",
                        },
                    },
                    "required": ["type", "kicker", "headline", "body"],
                },
            },
            "search_line": {
                "type": "string",
                "description": (
                    "인스타 캡션의 첫 줄. 40자 이내. 책 제목이 반드시 들어가야 한다. "
                    "구글과 인스타 검색에 잡히는 줄이므로 사람들이 실제로 검색할 만한 말로 써라. "
                    "예: '돈의 심리학 요약 — 투자가 자꾸 흔들린다면'. "
                    "해시태그를 여기 넣지 마라."
                ),
            },
            "hashtags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "# 를 포함한 해시태그. ★3~5개만. 많이 달수록 오히려 손해다.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "low"],
                "description": "주어진 자료가 빈약해 내용을 짐작해 썼다면 low.",
            },
        },
        "required": ["threads_text", "slides", "search_line", "hashtags", "confidence"],
    },
}

SYSTEM = """너는 책 소개 SNS 계정의 카피라이터다.

너에게 주어지는 것은 출판사가 쓴 홍보용 소개글과 목차다. 너는 책을 읽지 않았다.
따라서 '내가 읽어보니', '후반부가 특히' 같은 독서 경험을 지어내면 안 된다.

문체 — 이게 이 계정의 전부다:
- 설명하지 말고 보여줘라. '중요하다'고 쓰지 말고, 중요하다는 걸 느끼게 하는 장면을 써라.
- 개조식·보고서·시험문제 말투를 쓰지 마라. '~에 대하여', '~의 중요성', '~하는 방법' 금지.
- 문장을 짧게 끊어라. 한 문장에 한 가지만 담아라.
- 사람이 속으로 하는 말에 가깝게 써라. 독자가 '어 나 저런데' 하고 멈추게 만드는 것이 목표다.

구체성 — 이야기가 사느냐 죽느냐가 여기서 갈린다:
- 두루뭉술한 명사를 쓰지 마라. '앱'이 아니라 '증권 앱'. '숫자'가 아니라 화면에 뭐가 떠 있었는지.
  '일이 있었다'가 아니라 무슨 일이었는지. 독자가 머릿속에 그림을 그릴 수 있어야 한다.
- 시간·요일·장소·금액대·행동 중 최소 두 가지는 넣어라. '어느 화요일 점심시간에' 같은 것.
- ★이야기를 벌여놓고 결말 없이 끝내지 마라. '한참을 앉아 있었다', '많은 생각이 들었다' 처럼
  여운만 남기고 흐지부지 닫는 것이 가장 흔한 실패다. 그래서 어떻게 됐는지 반드시 보여줘라.
- 인물이 둘이면 마지막에 둘이 각각 어떻게 됐는지 대비시켜라. 한쪽만 결말이 나면 안 된다.
- 단, 지어낸 숫자를 통계나 실제 기록인 것처럼 쓰지 마라. 어디까지나 예시다.

지켜야 할 것:
1. 소개글의 문장을 그대로 옮기지 마라. 반드시 네 문장으로 다시 써라.
   같은 표현이 10자 이상 연달아 겹치면 실패다.
2. 자료에 없는 사실(판매부수, 수상 이력, 저자 경력)을 만들어내지 마라.
3. 과장 광고 문구를 쓰지 마라: 인생책, 필독, 충격, 화제의, 완벽한, 단 하나의.
4. 목차가 주어졌다면 그 책이 실제로 다루는 범위를 파악하는 근거로만 써라.
   목차를 그대로 나열하지 마라.
5. 결론적으로 '이 책은 어떤 상황의 사람에게 쓸모 있는가'를 한 문장으로 짚어라.
6. 책에 나오는 일화, 사례, 인용문을 절대 지어내지 마라. 이것이 가장 위험한 실수다.
   실존하는 책에 없는 내용을 있다고 쓰는 것이기 때문이다.
   '상황' 카드에서 일상 장면을 묘사할 때도, 그것이 네가 만든 예시임이 분명해야 하고
   책에서 가져온 것처럼 보이게 써서는 안 된다.

자료가 소개글 두세 줄뿐이라 내용을 알 수 없으면 confidence 를 low 로 두고,
아는 만큼만 담백하게 써라. 모르면 모르는 대로 두는 편이 지어내는 것보다 낫다."""


def _beat_guide(slide_plan: list[str]) -> str:
    """'이야기' 카드가 여러 장이면, 한 편을 몇 장면으로 나눠 쓰라고 알려줍니다."""
    positions = [i for i, t in enumerate(slide_plan, start=1) if t == "이야기"]
    if len(positions) < 2:
        return ""
    beats = [
        "장면을 열어라. 누가 어디서 무엇을 하고 있는지 구체적으로 보여주고 멈춰라. "
        "결과는 아직 말하지 마라."
    ]
    if len(positions) >= 3:
        beats.append("상황이 조여드는 대목. 아직 결론을 내지 마라.")
    beats.append(
        "★결말을 내는 장이다. 그래서 어떻게 됐는지 눈에 보이게 끝내라. "
        "인물이 둘이면 둘이 각각 어떻게 됐는지 대비시켜라. "
        "'한참을 앉아 있었다' 같이 여운만 남기고 닫으면 실패다."
    )
    while len(beats) < len(positions):
        beats.insert(-1, "이야기를 한 칸 더 밀고 나가라.")

    lines = [
        f"[이야기 카드 {len(positions)}장은 따로 노는 이야기가 아니다]",
        "한 편의 이야기를 장면으로 나눈 것이다. 등장인물과 상황을 끝까지 같게 유지하라.",
    ]
    lines += [
        f"  {pos}장({i + 1}번째 장면): {beat}"
        for i, (pos, beat) in enumerate(zip(positions, beats[: len(positions)]))
    ]
    lines.append(
        "두 번째 장면부터는 kicker '만' 빈 문자열로 두어라. 같은 이야기가 이어진다는 표시다. "
        "★headline 은 모든 장에서 반드시 채워라. 비우면 카드가 망가진다."
    )
    return "\n".join(lines)


def _prompt(book: dict, tone: str, slide_plan: list[str], flow: str = "이어지기") -> str:
    parts = [
        f"제목: {book['title']}",
        f"저자: {book['author']}",
        f"출판사: {book['publisher']}",
        f"출간일: {book['pub_date']}",
        f"분야: {book['category']}",
        "",
        "[출판사 소개글]",
        book["description"] or "(제공되지 않음)",
    ]
    if book.get("toc"):
        parts += ["", "[목차]", book["toc"][:1500]]
    plan = "\n".join(
        f"{i}장 [{t}] {SLIDE_TYPES[t]}" for i, t in enumerate(slide_plan, start=1)
    )
    parts += [
        "",
        f"[이 계정의 글투]\n{tone}",
        "",
        f"[인스타 카드 구성] 정확히 {len(slide_plan)}장을, 아래 순서와 종류 그대로 만들어라.",
        plan,
        "",
        FLOW_RULES.get(flow, FLOW_RULES["이어지기"]),
    ]
    beats = _beat_guide(slide_plan)
    if beats:
        parts += ["", beats]
    parts += ["", "write_post 도구를 사용해 답하라."]
    return "\n".join(parts)


def longest_overlap(a: str, b: str) -> int:
    """두 글 사이에 연속으로 똑같이 겹치는 가장 긴 길이. 표절 검사용."""
    a = "".join(a.split())
    b = "".join(b.split())
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def write_copy(book: dict, config: dict) -> dict:
    """책 한 권에 대한 문구를 생성합니다. 베낀 티가 나면 한 번 더 시도합니다."""
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    tone = config["글투"]["지침"]
    slide_plan = adapt_plan(slide_plan_from(config), book)
    flow = config.get("카드구성", {}).get("흐름", "이어지기")
    model = config["모델"]["이름"]

    prompt = _prompt(book, tone, slide_plan, flow)
    warning = ""

    for attempt in range(2):
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "write_post"},
            messages=[{"role": "user", "content": prompt + warning}],
        )
        result = next(
            (b.input for b in message.content if b.type == "tool_use"), None
        )
        if result is None:
            raise RuntimeError("Claude가 문구를 만들지 못했습니다.")

        overlap = longest_overlap(result["threads_text"], book["description"])
        if overlap < COPY_OVERLAP_LIMIT or attempt == 1:
            result["copy_overlap"] = overlap
            result["model"] = model
            break

        warning = (
            f"\n\n[다시 작성] 방금 쓴 문구에 출판사 소개글과 {overlap}자가 "
            "그대로 겹치는 부분이 있었다. 표현을 완전히 바꿔 다시 써라."
        )

    result["hashtags"] = _merge_hashtags(result.get("hashtags", []), config)
    result["threads_text"] = _trim(result["threads_text"])
    result["slides"] = apply_plan(slide_plan, result.get("slides", []), book)
    result["search_line"] = _search_line(result.get("search_line", ""), book)
    if len(book.get("description") or "") < THIN_SOURCE:
        # 자료가 이만큼 짧으면 무슨 말을 쓰든 얕을 수밖에 없습니다.
        result["confidence"] = "low"
    return result


def apply_plan(plan: list[str], slides: list[dict], book: dict) -> list[dict]:
    """카드 종류를 계획대로 덮어쓰고 대체텍스트를 붙입니다.

    모델이 시킨 종류를 무시하고 다른 종류로 보내거나, 이어지는 카드에서
    종류를 빈 값으로 보내는 일이 실제로 있었습니다. 계획이 정답입니다.
    """
    return [
        {**slide, "type": kind, "alt": _alt_text(slide, book)}
        for kind, slide in zip(plan, slides)
    ]


def adapt_plan(plan: list[str], book: dict) -> list[str]:
    """자료에 없는 것을 요구하는 카드는 다른 종류로 바꿉니다.

    목차가 없는데 '질문' 카드를 시키면 모델이 목차를 지어냅니다.
    알라딘 API는 제휴 파트너가 아니면 목차를 주지 않습니다.
    """
    if book.get("toc"):
        return plan
    swapped = ["상황" if t == "질문" else t for t in plan]
    if swapped != plan:
        print("    (목차가 없어 '질문' 카드를 '상황'으로 바꿨습니다)")
    return swapped


def _alt_text(slide: dict, book: dict) -> str:
    """대체텍스트를 카드 내용에서 직접 만듭니다.

    모델에게 맡겼더니 '흰 배경에 책 표지', '초록색 벨트 위에 종이배' 처럼
    있지도 않은 사진을 묘사했습니다. 이 카드는 어두운 배경에 글자만 있어서
    그런 설명은 전부 거짓이 됩니다. 그래서 카드에 실제로 적힌 글에서 만듭니다.
    (인스타 검색이 읽는 문장이라 책 제목이 들어가야 하고, 100자를 넘으면 거부됩니다)
    """
    title = book.get("short_title") or book["title"]
    headline = " ".join((slide.get("headline") or "").split())
    body = " ".join((slide.get("body") or "").split())

    alt = f"{title} 소개 카드"
    # 헤드라인이 비어 오는 경우가 있어(이어지는 장면 카드) 본문으로 대신합니다.
    lead = headline or body
    if lead:
        alt = f"{alt}: {lead}"
    if body and body != lead and len(alt) + len(body) + 2 <= 100:
        alt = f"{alt}. {body}"
    return _cut_words(alt, 100)


def _search_line(line: str, book: dict) -> str:
    """캡션 첫 줄. 검색에 잡히는 줄이라 책 제목이 반드시 들어가야 합니다.

    긴 부제까지 들어가면 60자를 넘겨 어중간하게 잘리므로 짧은 제목을 씁니다.
    """
    title = book.get("short_title") or book["title"]
    line = " ".join((line or "").split()).lstrip("#").strip()

    # 모델이 제목을 이미 넣었다면 그 부분을 떼고 뒷말만 씁니다.
    for candidate in (book["title"], title):
        if candidate and line.startswith(candidate):
            line = line[len(candidate) :].lstrip(" —-–:·").strip()
            break

    if not line:
        return f"{title} 요약"
    # 모델이 '앞말 — 뒷말' 로 보내면 제목까지 붙어 줄표가 두 개가 됩니다. 앞말만 씁니다.
    line = re.split(r"\s[—–-]\s", line)[0].strip()
    return _cut_words(f"{title} — {line}", 60)


def _cut_words(text: str, limit: int) -> str:
    """글자 수 제한에 맞추되 단어 중간에서 끊지 않습니다."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" —-–,·").strip()


def slide_plan_from(config: dict) -> list[str]:
    """설정에서 카드 구성을 읽습니다. 잘못 적힌 종류는 걸러냅니다."""
    order = config.get("카드구성", {}).get("순서") or []
    plan = [t for t in order if t in SLIDE_TYPES]
    unknown = [t for t in order if t not in SLIDE_TYPES]
    if unknown:
        print(
            f"  ! config.json 의 카드 종류 {unknown} 는 없는 종류라 건너뜁니다. "
            f"쓸 수 있는 종류: {', '.join(SLIDE_TYPES)}"
        )
    return plan or ["훅", "핵심", "정리"]


def _merge_hashtags(generated: list[str], config: dict) -> list[str]:
    fixed = config["글투"].get("해시태그", [])
    merged, seen = [], set()
    for tag in list(fixed) + list(generated):
        tag = tag.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        if tag not in seen:
            seen.add(tag)
            merged.append(tag)
    # 해시태그는 많이 달수록 손해. 5개에서 끊습니다.
    return merged[:5]


def _trim(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_THREADS_CHARS:
        return text
    cut = text[:MAX_THREADS_CHARS]
    stop = max(cut.rfind("."), cut.rfind("\n"), cut.rfind("다"))
    return (cut[: stop + 1] if stop > MAX_THREADS_CHARS * 0.6 else cut).strip()


def compose_threads_text(
    draft_text: str, hashtags: str, link: str, credit: str = ""
) -> str:
    """실제로 발행할 최종 본문. 500자 한도를 넘지 않게 뒤에서부터 줄입니다.

    링크와 출처 표기는 알라딘 상위 등급 승인 조건이라 끝까지 지키고,
    자리가 모자라면 해시태그부터 덜어냅니다. 그래도 넘치면 본문을 줄입니다.
    """

    def build(body: str, tags: str) -> str:
        return "\n\n".join(p for p in [body.strip(), tags.strip(), link.strip(), credit.strip()] if p)

    text = build(draft_text, hashtags)
    if len(text) <= 500:
        return text

    tags = hashtags.split()
    while tags:
        tags.pop()
        text = build(draft_text, " ".join(tags))
        if len(text) <= 500:
            return text

    # 해시태그를 다 빼도 넘치면 본문을 줄입니다.
    fixed = len(build("", ""))
    body = _trim_to(draft_text, max(0, 500 - fixed - 2))
    return build(body, "")[:500]


def _trim_to(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind("."), cut.rfind("\n"), cut.rfind("다"))
    return (cut[: stop + 1] if stop > limit * 0.5 else cut).strip()
