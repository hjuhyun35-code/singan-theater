"""이미 만들어진 초안으로 세로 영상(릴스)을 만듭니다.

문구는 초안의 slides 를 그대로 씁니다. 모델을 다시 부르지 않으므로 돈이 안 듭니다.

만드는 순서
  1. 장면마다 '읽을 말'을 정합니다.
  2. edge-tts 로 그 말을 읽혀 mp3 를 얻고, 길이를 잽니다.
  3. 그 길이에 맞춰 장면 시간표를 짭니다. (말이 끝나기 전에 화면이 넘어가면 안 됩니다)
  4. 크롬으로 1초에 24장씩 화면을 찍습니다.
  5. ffmpeg 로 그림과 소리를 합쳐 mp4 를 만듭니다.

ffmpeg 는 GitHub 서버에 **없습니다**. 워크플로에서 apt 로 깔아야 합니다
(telegram.yml 의 'ffmpeg 설치' 단계). 없으면 ffprobe 없음으로 죽습니다.

★ 음악은 넣지 않습니다. 읽는 소리만 들어갑니다.
  인스타 앱의 음악 목록은 API 로 못 붙이므로, 음악을 원하면 앱에서 직접 올리세요.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

# 카드와 같은 굵은 한글 글꼴(검은고딕)을 씁니다. 저장소 안에 들어 있어
# GitHub 서버에서도 똑같이 나옵니다.
from .card import display_font_uri

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 1080, 1920
FPS = 24
MIN_SCENE = 2.6
JPEG_QUALITY = 92

_env = Environment(
    loader=FileSystemLoader(str(ROOT / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _plain(text: str) -> str:
    """*강조* 표시를 걷어낸 맨 글자. 읽어줄 때 씁니다."""
    return re.sub(r"\*(.+?)\*", r"\1", text or "").strip()


def _first_sentences(text: str, n: int) -> str:
    """앞에서 문장 n 개만. 릴스에서 본문을 통째로 읽으면 너무 깁니다."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(p for p in parts[:n] if p).strip()


def build_script(post: dict, config: dict, note: str = "") -> list[dict]:
    """장면 목록을 만듭니다.

    기본은 릴스 전용 대본입니다. 카드 문구를 그대로 읽으면 '여운' 으로 끝나
    흐지부지합니다. 릴스는 훅 → 핵심 3포인트 → CTA 로 닫아야 끝까지 봅니다.
    대본 쓰는 값은 아주 적습니다(하이쿠 한 번, 웹 검색 없음).

    대본 만들기가 실패하면 예전 방식(카드 문구 그대로)으로 물러섭니다.
    영상이 아예 안 나오는 것보다 낫습니다.
    """
    if config.get("영상", {}).get("전용대본", True):
        try:
            from . import reelscript

            scenes, caption = reelscript.write_script(post, config, note)
            return scenes, caption
        except Exception as exc:
            print(f"  ! 릴스 대본 실패, 카드 문구로 만듭니다: {exc}")
    # 물러섰을 때는 초안이 이미 갖고 있는 캡션을 그대로 씁니다.
    return build_script_from_cards(post, config), post.get("caption", "")


def build_script_from_cards(post: dict, config: dict) -> list[dict]:
    """카드뉴스 문구를 그대로 읽는 예전 방식. 대본 만들기가 실패했을 때만 씁니다.

    전부 읽으면 90초가 넘어 릴스로 너무 깁니다. 그래서 자리마다 읽는 양을 다르게 둡니다.
      훅·여운 = 제목 + 본문 앞 두 문장   (시작과 끝은 붙잡아야 합니다)
      이야기  = 제목만                   (장면 전환을 빠르게)
      핵심    = 제목 + 본문 한 문장
    """
    rule = {"훅": 2, "이야기": 0, "상황": 0, "핵심": 1, "질문": 1, "정리": 1, "여운": 2}
    scenes: list[dict] = []
    for s in post.get("slides", []):
        head = _plain(s.get("headline", ""))
        if not head:
            continue
        n = rule.get(s.get("type", ""), 1)
        body = _first_sentences(s.get("body", ""), n) if n else ""
        scenes.append(
            {
                "kind": s.get("type", ""),
                "kicker": s.get("kicker", ""),
                "headline": head,
                "emphasis": _plain(s.get("emphasis", "")),
                "body": body,
                "say": f"{head}. {body}".strip().rstrip("."),
            }
        )

    # 마지막은 표지와 책 정보. 맺음말로 확실히 닫습니다.
    # 이 한 줄이 없으면 소리가 그냥 끊겨 '끝난 것 같지 않다' 는 느낌이 납니다.
    title = post.get("short_title") or post.get("title", "")
    author = post.get("author", "")
    closing = config.get("영상", {}).get("맺음말", "매일 한 권, 신간극장")
    scenes.append(
        {
            "kind": "표지",
            "kicker": "",
            "headline": title,
            "emphasis": "",
            "body": author,
            "outro_line": closing,
            "say": f"{title}. {author}. {closing}",
        }
    )
    return scenes


async def _speak(text: str, voice: str, rate: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def _duration(path: Path) -> float:
    """소리 파일 길이(초). ffprobe 는 ffmpeg 와 같이 깔려 있습니다."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def narrate(
    scenes: list[dict], work: Path, voice: str, rate: str, gap: float, tails: dict
) -> list[dict]:
    """장면마다 소리를 만들고 시간표를 짭니다.

    큰 글씨(제목)와 본문을 따로 읽힙니다. 한 덩어리로 읽으면 큰 글씨가 뜨자마자
    설명이 붙어 숨 쉴 틈이 없습니다. 사이에 gap 만큼 조용히 둡니다.
    끝나는 장면(여운·표지)은 tail 을 길게 잡아 더 머무릅니다.
    """
    plan: list[dict] = []
    for i, sc in enumerate(scenes):
        head_mp3 = work / f"h{i:02d}.mp3"
        asyncio.run(_speak(sc["headline"], voice, rate, head_mp3))
        head_len = _duration(head_mp3)

        body_mp3, body_len = None, 0.0
        if sc["body"]:
            body_mp3 = work / f"b{i:02d}.mp3"
            asyncio.run(_speak(sc["body"], voice, rate, body_mp3))
            body_len = _duration(body_mp3)

        tail = tails.get(sc["kind"], tails["기본"])
        spoken = head_len + (gap + body_len if body_mp3 else 0.0)
        dur = max(MIN_SCENE, spoken + tail)
        plan.append(
            {
                "head": head_mp3,
                "body": body_mp3,
                "body_start": head_len + gap,
                "dur": dur,
                "tail": tail,
            }
        )
        print(
            f"  {i+1}번 장면 {dur:.1f}초 (읽기 {spoken:.1f} + 여운 {tail:.1f})"
            f"  {sc['headline'][:20]}…"
        )
    return plan


# 썸네일 글자 자리 (1080x1920 기준). 실측으로 잡은 값입니다.
_TW = 940.0    # 글자가 들어갈 가로 (1080 - 양옆 여백 70)
_TH = 790.0    # 표지 아래부터 책 제목 위까지 쓸 세로. 실제 자리는 876 이지만 여유를 둡니다.
_EM = 0.79     # 검은고딕 글자 하나가 차지하는 폭 (2026-08-22 크롬에서 실측)
_GAP = 0.22    # 낱말 사이 여백


def _line_count(words: list[str], size: int) -> int:
    """그 크기로 쓰면 몇 줄이 되는지 실제로 채워봅니다.

    '전체 글자 수 나누기 한 줄 글자 수' 로 어림했다가 크게 틀렸습니다.
    낱말은 중간에서 안 잘리므로 줄 끝에 자리가 모자라면 통째로 다음 줄로 넘어갑니다.
    그래서 어림값보다 줄이 훨씬 많이 나옵니다(3줄로 봤는데 실제 5줄).
    """
    lines, cur = 1, 0.0
    for w in words:
        # ★ 낱말 뒤 여백은 줄 끝에서도 자리를 차지합니다. 낱말 '사이' 로만 세면
        #   실제보다 줄을 적게 잡습니다(3줄로 봤는데 브라우저는 5줄).
        box = len(w) * _EM * size + _GAP * size
        if cur > 0 and cur + box > _TW:
            lines += 1
            cur = box
        else:
            cur += box
    return lines


def _head_size(headline: str) -> int:
    """썸네일 큰 글씨 크기를 문장에 맞춰 정합니다.

    가로(가장 긴 낱말이 한 줄에 들어갈 것)와 세로(책 제목과 안 겹칠 것)를
    둘 다 만족하는 가장 큰 크기를 고릅니다.
    """
    words = (headline or "").split()
    if not words:
        return 160
    longest = max(len(w) for w in words)
    for size in range(240, 96, -4):
        # 가장 긴 낱말 하나가 줄을 넘으면 한글은 글자 사이에서 잘립니다.
        # ('드라큘라가' 가 '드라큘라 / 가' 로 쪼개짐) 뒤 여백까지 넣어 막습니다.
        if longest * _EM * size + _GAP * size > _TW:
            continue
        if _line_count(words, size) * size * 1.02 <= _TH:
            return size
    return 100


def _body_parts(body: str, hot: str) -> list[dict]:
    """설명글을 '보통 / 강조 / 보통' 으로 쪼갭니다.

    소리를 끄고 보는 사람에게는 이 색이 '어디를 봐야 하는지' 를 알려줍니다.
    모델이 대사에 없는 말을 강조로 적어 보내면 그냥 통째로 보통 글이 됩니다.
    """
    body = body or ""
    hot = (hot or "").strip()
    if not hot or hot not in body:
        return [{"t": body, "hot": False}]
    i = body.index(hot)
    return [
        {"t": body[:i], "hot": False},
        {"t": hot, "hot": True},
        {"t": body[i + len(hot) :], "hot": False},
    ]


def _words(headline: str, emphasis: str) -> list[dict]:
    """제목을 낱말로 쪼갭니다. 한 낱말씩 튀어나오게 하려는 것입니다.

    강조는 '겹치면 칠한다' 로 봅니다. 낱말이 강조 문구와 글자까지 똑같아야
    칠하게 했더니 거의 안 칠해졌습니다. 한국어는 조사가 붙어서
    모델이 '허구' 라고 지정해도 화면의 낱말은 '허구다' 입니다.
    (2026-08-10 실측: 다섯 경우 중 하나만 칠해졌습니다)
    """
    words = headline.split()
    lo = headline.find(emphasis) if emphasis else -1
    if lo < 0 and emphasis:
        # 강조 문구가 통째로는 없을 때. 낱말 하나라도 서로를 품고 있으면 그걸 씁니다.
        for w in words:
            # 한 글자짜리는 아무 데나 걸립니다('말' 이 '전혀다른말' 안에 들어 있듯이).
            if len(w) >= 2 and (w in emphasis or emphasis in w):
                lo = headline.find(w)
                emphasis = w
                break
    hi = lo + len(emphasis) if lo >= 0 else -1

    out, pos = [], 0
    for w in words:
        i = headline.index(w, pos)
        pos = i + len(w)
        # 낱말이 강조 구간과 조금이라도 겹치면 칠합니다.
        out.append({"text": w, "hot": lo >= 0 and i < hi and pos > lo})
    return out


def render_frames(
    scenes: list[dict],
    plan: list[dict],
    cover_url: str,
    theme: str,
    accent: str | None,
    frames_dir: Path,
) -> int:
    """장면들을 한 장짜리 HTML 로 만들고, 1초에 24장씩 찍습니다.

    CSS 애니메이션을 그냥 두면 찍는 시점마다 어긋납니다. 그래서 애니메이션을
    멈춰 세우고 '지금 몇 초' 를 직접 지정한 뒤 찍습니다. 프레임이 정확히 맞습니다.
    """
    starts, t = [], 0.0
    for item in plan:
        starts.append(t)
        t += item["dur"]
    total = t

    # 강조가 실제로 칠해졌는지 눈으로 확인할 수 있게 찍어둡니다.
    # 안 칠해지는 걸 두 번이나 못 알아채서 넣었습니다.
    for sc in scenes:
        marked = [w["text"] for w in _words(sc["headline"], sc.get("emphasis", "")) if w["hot"]]
        print(
            f"    제목 강조: {sc.get('emphasis','') or '(지정 없음)'} "
            f"→ {marked or '칠해진 낱말 없음 ⚠'}  [{sc['headline']}]"
        )

    html = _env.get_template("reel.html").render(
        scenes=[
            {**sc, "words": _words(sc["headline"], sc["emphasis"]),
             "body_parts": _body_parts(sc.get("body", ""), sc.get("body_hot", "")),
             # 썸네일 장면만 글씨 크기를 따로 정합니다. 나머지는 서식의 기본값을 씁니다.
             "head_size": _head_size(sc["headline"]) if sc.get("kind") == "표지" else 0,
             "start": starts[i], "dur": plan[i]["dur"],
             # 본문 글은 본문을 읽기 시작할 때 맞춰 뜹니다. 낱말 수로 어림잡던 것보다 정확합니다.
             "body_at": plan[i]["body_start"], "index": i}
            for i, sc in enumerate(scenes)
        ],
        cover_url=cover_url,
        theme=theme,
        accent=accent,
        total=total,
        display_font=display_font_uri(),
    )

    frames_dir.mkdir(parents=True, exist_ok=True)
    count = int(total * FPS)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(400)  # 글꼴과 표지 그림이 자리를 잡을 시간
        for n in range(count):
            page.evaluate(
                "ms => document.getAnimations().forEach(a => { a.pause(); a.currentTime = ms; })",
                (n / FPS) * 1000,
            )
            page.screenshot(
                path=str(frames_dir / f"{n:05d}.jpg"), type="jpeg", quality=JPEG_QUALITY
            )
        browser.close()
    print(f"  화면 {count}장 ({total:.1f}초)")
    return count


def _to_wav(src: Path, dst: Path) -> Path:
    """이어붙이기 전에 형식을 통일합니다. 섞여 있으면 concat 이 어긋납니다."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ar", "44100", "-ac", "2", str(dst)],
        check=True,
    )
    return dst


def _silence(seconds: float, dst: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds:.3f}", str(dst)],
        check=True,
    )
    return dst


def build_audio(plan: list[dict], work: Path, gap: float) -> Path:
    """제목 → 조용함 → 본문 → 조용함 순으로 이어붙여 한 줄기 소리를 만듭니다.

    장면 길이에 정확히 맞춰 뒤를 채웁니다. 안 그러면 소리와 화면이 밀립니다.
    """
    hush = _silence(gap, work / "gap.wav")
    padded = []
    for i, item in enumerate(plan):
        pieces = [_to_wav(item["head"], work / f"hw{i:02d}.wav")]
        if item["body"]:
            pieces += [hush, _to_wav(item["body"], work / f"bw{i:02d}.wav")]

        part_list = work / f"p{i:02d}.txt"
        part_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in pieces), encoding="utf-8"
        )
        out = work / f"pad{i:02d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(part_list),
             "-af", f"apad=whole_dur={item['dur']:.3f}", "-t", f"{item['dur']:.3f}",
             "-ar", "44100", "-ac", "2", str(out)],
            check=True,
        )
        padded.append(out)

    listing = work / "list.txt"
    listing.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in padded), encoding="utf-8"
    )
    joined = work / "voice.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c:a", "aac", "-b:a", "160k", str(joined)],
        check=True,
    )
    return joined


def mux(frames_dir: Path, audio: Path, out: Path) -> Path:
    """그림과 소리를 합쳐 인스타가 받아주는 mp4 로 만듭니다.

    yuv420p 와 +faststart 를 빼면 인스타가 거부하거나 재생이 늦게 시작됩니다.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-framerate", str(FPS), "-i", str(frames_dir / "%05d.jpg"),
         "-i", str(audio),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
         "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)],
        check=True,
    )
    return out


def make_reel(post: dict, config: dict, out_path: Path, note: str = "") -> dict:
    """초안 하나로 릴스 영상 한 편을 만듭니다.

    돌려주는 것: {"path": 영상 파일, "caption": 인스타에 붙여넣을 글}
    """
    설정 = config.get("영상", {})
    voice = 설정.get("목소리", "ko-KR-SunHiNeural")
    rate = 설정.get("말속도", "+6%")
    gap = float(설정.get("쉼", 0.85))
    tails = {
        "기본": float(설정.get("여운", 0.9)),
        # 마무리는 길게 머무릅니다. 바로 끊기면 남는 게 없습니다.
        "여운": float(설정.get("끝여운", 2.4)),
        "표지": float(설정.get("끝여운", 2.4)),
    }

    scenes, caption = build_script(post, config, note)
    work = Path(tempfile.mkdtemp(prefix="reel-"))
    try:
        print(f"  목소리 {voice} · 속도 {rate} · 쉼 {gap}초 · 끝여운 {tails['여운']}초")
        plan = narrate(scenes, work, voice, rate, gap, tails)
        render_frames(
            scenes,
            plan,
            post.get("cover_url", "") or post.get("cover_url_fallback", ""),
            config.get("발행", {}).get("색테마", "종이"),
            None,
            work / "frames",
        )
        audio = build_audio(plan, work, gap)
        mux(work / "frames", audio, out_path)
        print(f"  영상 완성: {out_path.name} ({out_path.stat().st_size/1e6:.1f}MB)")
        return {"path": out_path, "caption": caption}
    finally:
        shutil.rmtree(work, ignore_errors=True)
