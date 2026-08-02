"""카드 이미지를 인터넷에 올려 '공개 주소'를 만듭니다.

쓰레드와 인스타 API는 내 컴퓨터의 파일을 직접 못 받습니다.
반드시 https:// 로 시작하는 공개된 이미지 주소를 줘야 하므로,
무료 이미지 호스팅(imgbb)에 먼저 올립니다.
"""

import base64
from pathlib import Path

import requests

from .settings import env

IMGBB_URL = "https://api.imgbb.com/1/upload"
TIMEOUT = 60


def upload(path: str | Path) -> str:
    """이미지 파일 하나를 올리고 공개 주소를 돌려줍니다."""
    key = env("IMGBB_API_KEY", required=True)
    data = Path(path).read_bytes()
    resp = requests.post(
        IMGBB_URL,
        data={"key": key, "image": base64.b64encode(data).decode("ascii")},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"이미지 업로드 실패({resp.status_code}): {resp.text[:200]}")
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"이미지 업로드 실패: {payload}")
    return payload["data"]["url"]


def upload_all(paths: list[str]) -> list[str]:
    return [upload(p) for p in paths]
