"""쓰레드와 인스타그램에 실제로 글을 올립니다.

두 플랫폼 모두 방식이 같습니다.
  1) '컨테이너'를 만든다 (아직 안 올라감)
  2) 서버가 이미지를 다 받을 때까지 기다린다
  3) publish 를 호출하면 그때 올라간다
"""

import time

import requests

from .settings import env

THREADS_HOST = "https://graph.threads.net/v1.0"
INSTAGRAM_HOST = "https://graph.instagram.com/v23.0"
TIMEOUT = 60
POLL_INTERVAL = 5
POLL_MAX = 24  # 최대 2분 대기


class PublishError(RuntimeError):
    pass


def _post(url: str, params: dict) -> dict:
    resp = requests.post(url, data=params, timeout=TIMEOUT)
    payload = _json(resp)
    if resp.status_code >= 400 or "error" in payload:
        raise PublishError(_error_message(payload, resp))
    return payload


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    payload = _json(resp)
    if resp.status_code >= 400 or "error" in payload:
        raise PublishError(_error_message(payload, resp))
    return payload


def _drop_empty(params: dict) -> dict:
    """값이 빈 항목은 아예 보내지 않습니다. 빈 alt_text 를 보내면 거부될 수 있습니다."""
    return {k: v for k, v in params.items() if v not in (None, "")}


def _fit_alts(alt_texts: list[str] | None, count: int) -> list[str]:
    """대체텍스트를 이미지 수에 맞추고, 100자 제한을 지킵니다."""
    alts = list(alt_texts or [])
    alts += [""] * (count - len(alts))
    return [(a or "").strip()[:100] for a in alts[:count]]


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": {"message": resp.text[:300]}}


def _error_message(payload: dict, resp: requests.Response) -> str:
    err = payload.get("error", {})
    msg = err.get("message") or resp.text[:300]
    code = err.get("code")
    hint = ""
    if code in (190, 102):
        hint = "  → 토큰이 만료됐습니다. tools/refresh_tokens.py 를 실행하세요."
    elif code == 10 or "permission" in str(msg).lower():
        hint = "  → Meta 앱에 권한(scope)이 빠졌습니다. 설정안내.md 를 확인하세요."
    return f"{msg} (code={code}){hint}"


def _wait_ready(host: str, container_id: str, token: str, status_field: str) -> None:
    """서버가 이미지를 다 받았는지 확인합니다. 바로 publish 하면 실패합니다."""
    for _ in range(POLL_MAX):
        info = _get(
            f"{host}/{container_id}",
            {"fields": f"{status_field},error_message", "access_token": token},
        )
        status = info.get(status_field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(
                f"이미지 처리 실패: {info.get('error_message') or status}"
            )
        time.sleep(POLL_INTERVAL)
    raise PublishError("이미지 처리가 2분 안에 끝나지 않았습니다. 잠시 후 다시 시도하세요.")


# ----------------------------------------------------------------- 쓰레드


def post_to_threads(text: str, image_urls: list[str] | None = None) -> str:
    user_id = env("THREADS_USER_ID", required=True)
    token = env("THREADS_ACCESS_TOKEN", required=True)
    base = f"{THREADS_HOST}/{user_id}"
    image_urls = image_urls or []

    if not image_urls:
        container = _post(
            f"{base}/threads",
            {"media_type": "TEXT", "text": text, "access_token": token},
        )["id"]
    elif len(image_urls) == 1:
        container = _post(
            f"{base}/threads",
            {
                "media_type": "IMAGE",
                "image_url": image_urls[0],
                "text": text,
                "access_token": token,
            },
        )["id"]
    else:
        children = [
            _post(
                f"{base}/threads",
                {
                    "media_type": "IMAGE",
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": token,
                },
            )["id"]
            for url in image_urls[:20]
        ]
        container = _post(
            f"{base}/threads",
            {
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "text": text,
                "access_token": token,
            },
        )["id"]

    if image_urls:
        _wait_ready(THREADS_HOST, container, token, "status")
    else:
        time.sleep(3)

    return _post(
        f"{base}/threads_publish",
        {"creation_id": container, "access_token": token},
    )["id"]


# --------------------------------------------------------------- 인스타그램


def post_to_instagram(
    caption: str, image_urls: list[str], alt_texts: list[str] | None = None
) -> str:
    """대체텍스트(alt_text)는 인스타 검색이 읽습니다. 비워두면 그만큼 손해입니다."""
    if not image_urls:
        raise PublishError("인스타그램은 이미지 없이 올릴 수 없습니다.")

    user_id = env("INSTAGRAM_USER_ID", required=True)
    token = env("INSTAGRAM_ACCESS_TOKEN", required=True)
    base = f"{INSTAGRAM_HOST}/{user_id}"
    alts = _fit_alts(alt_texts, len(image_urls))

    if len(image_urls) == 1:
        container = _post(
            f"{base}/media",
            _drop_empty(
                {
                    "image_url": image_urls[0],
                    "caption": caption,
                    "alt_text": alts[0],
                    "access_token": token,
                }
            ),
        )["id"]
    else:
        children = [
            _post(
                f"{base}/media",
                _drop_empty(
                    {
                        "image_url": url,
                        "is_carousel_item": "true",
                        "alt_text": alt,
                        "access_token": token,
                    }
                ),
            )["id"]
            # 인스타 캐러셀은 최대 10장
            for url, alt in list(zip(image_urls, alts))[:10]
        ]
        container = _post(
            f"{base}/media",
            {
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "caption": caption,
                "access_token": token,
            },
        )["id"]

    _wait_ready(INSTAGRAM_HOST, container, token, "status_code")

    return _post(
        f"{base}/media_publish",
        {"creation_id": container, "access_token": token},
    )["id"]


def instagram_quota() -> dict:
    """오늘 API로 몇 개나 올렸는지 확인합니다. 하루 100개 제한."""
    user_id = env("INSTAGRAM_USER_ID", required=True)
    token = env("INSTAGRAM_ACCESS_TOKEN", required=True)
    return _get(
        f"{INSTAGRAM_HOST}/{user_id}/content_publishing_limit",
        {"fields": "config,quota_usage", "access_token": token},
    )
