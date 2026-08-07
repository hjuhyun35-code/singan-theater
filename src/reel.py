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


def build_script(post: dict, config: dict) -> list[dict]:
    """장면 목록을 만듭니다. 각 장면에는 화면에 띄울 글과 읽어줄 말이 들어갑니다.

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

    # 마지막은 표지와 책 정보. 여기서 계정 이름을 남깁니다.
    scenes.append(
        {
            "kind": "표지",
            "kicker": "",
            "headline": post.get("short_title") or post.get("title", ""),
            "emphasis": "",
            "body": post.get("author", ""),
            "say": f"{post.get('short_title') or post.get('title', '')}. {post.get('author', '')}",
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


def _words(headline: str, emphasis: str) -> list[dict]:
    """제목을 낱말로 쪼갭니다. 한 낱말씩 튀어나오게 하려는 것입니다."""
    out = []
    for w in headline.split():
        out.append({"text": w, "hot": bool(emphasis) and w in emphasis})
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

    html = _env.get_template("reel.html").render(
        scenes=[
            {**sc, "words": _words(sc["headline"], sc["emphasis"]),
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


def make_reel(post: dict, config: dict, out_path: Path) -> Path:
    """초안 하나로 릴스 영상 한 편을 만듭니다."""
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

    scenes = build_script(post, config)
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
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
