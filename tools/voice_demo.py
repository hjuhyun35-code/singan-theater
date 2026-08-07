"""목소리를 골라보려고 견본을 만들어 텔레그램으로 보냅니다.

edge-tts 가 실제로 가진 한국어 목소리 목록을 받아와서, 같은 문장을 목소리마다
읽혀 보냅니다. 이름을 외워 적으면 없는 목소리를 넣어 실패하기 쉬워서
목록을 직접 물어보는 방식으로 두었습니다.

  VOICE_GENDER=Female python tools/voice_demo.py
  VOICE_TEXT="읽을 문장" python tools/voice_demo.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import edge_tts
import requests

API = "https://api.telegram.org/bot{token}/{method}"

# 릴스에서 실제로 읽는 투와 가장 비슷한 문장을 씁니다.
# 짧은 인사말로 고르면 막상 본문에서 느낌이 다릅니다.
DEFAULT_TEXT = (
    "불탄 것들을 다시 세운다는 것. "
    "혼돈은 밖에서 부숴오기도, 안에서 무너뜨리기도 한다. "
    "그래도 누군가는 잿더미에서 시작한다."
)


async def korean_voices(gender: str) -> list[dict]:
    voices = await edge_tts.list_voices()
    picked = [
        v for v in voices
        if v.get("Locale") == "ko-KR" and (not gender or v.get("Gender") == gender)
    ]
    return sorted(picked, key=lambda v: v["ShortName"])


def send_audio(path: Path, title: str, caption: str, token: str, chat: str) -> None:
    with path.open("rb") as f:
        r = requests.post(
            API.format(token=token, method="sendAudio"),
            data={"chat_id": chat, "title": title, "performer": "신간극장 목소리 견본",
                  "caption": caption},
            files={"audio": (path.name, f, "audio/mpeg")},
            timeout=120,
        )
    if r.status_code != 200 or not r.json().get("ok"):
        raise RuntimeError(f"전송 실패({title}): {r.text[:200]}")


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("텔레그램 열쇠가 없습니다.")
        return 1

    gender = os.environ.get("VOICE_GENDER", "Female").strip()
    text = (os.environ.get("VOICE_TEXT") or "").strip() or DEFAULT_TEXT
    rate = os.environ.get("VOICE_RATE", "+6%")

    voices = asyncio.run(korean_voices(gender))
    if not voices:
        print(f"{gender} 한국어 목소리를 찾지 못했습니다.")
        return 1

    print(f"{len(voices)}개를 보냅니다. 문장: {text[:30]}…")
    work = Path(tempfile.mkdtemp(prefix="voice-"))
    for i, v in enumerate(voices, 1):
        name = v["ShortName"]
        mp3 = work / f"{name}.mp3"
        asyncio.run(edge_tts.Communicate(text, name, rate=rate).save(str(mp3)))
        # 사람이 알아볼 수 있게 성격 설명을 같이 붙입니다.
        note = ", ".join(
            v.get("VoiceTag", {}).get("VoicePersonalities", []) or []
        )
        send_audio(
            mp3,
            f"{i}. {name}",
            f"{i}번 · {name}\n{note or '설명 없음'}\n\n"
            f"이 목소리로 하려면 '{i}번' 이라고 알려주세요.",
            token,
            chat,
        )
        print(f"  {i}. {name}  ({note})")

    requests.post(
        API.format(token=token, method="sendMessage"),
        data={"chat_id": chat,
              "text": f"목소리 견본 {len(voices)}개를 보냈습니다.\n"
                      "마음에 드는 번호를 알려주시면 바꿔드리겠습니다."},
        timeout=30,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
