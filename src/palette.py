"""책 표지에서 강조색을 뽑습니다.

표지가 붉으면 카드의 강조선과 라벨도 붉게 갑니다.
표지와 카드가 한 세트로 보이고, 매일 같은 색이 반복되지 않습니다.

배경에 묻히면 안 되므로, 뽑은 색의 밝기를 테마에 맞게 조정합니다.
"""

import colorsys
import io

# 테마별로 강조색이 있어야 할 밝기 범위 (0~1)
# 어두운 배경엔 밝은 강조색, 밝은 배경엔 어두운 강조색이 필요합니다.
THEME_LIGHTNESS = {
    "밤": (0.55, 0.78),
    "쪽빛": (0.58, 0.80),
    "아이보리": (0.30, 0.48),
    "종이": (0.28, 0.46),
}
# 이보다 흐리면 강조색으로 쓸 만한 '색'이 아닙니다.
# 낮게 잡았더니 표지의 크림색·미색 배경을 골라 흐린 노란 강조선이 나왔습니다.
# 선명한 색이 없는 표지는 색을 뽑지 않고 테마 기본색을 그대로 씁니다.
MIN_SATURATION = 0.45


def _hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def accent_from_cover(image_bytes: bytes, theme: str = "밤") -> str | None:
    """표지에서 가장 눈에 띄는 색 하나를 골라 테마에 맞게 다듬습니다.

    고를 만한 색이 없으면(흑백 표지 등) None 을 돌려주고,
    그러면 테마 기본 강조색을 그대로 씁니다.
    """
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    img.thumbnail((96, 96))
    counts: dict[tuple[int, int, int], int] = {}
    for r, g, b in img.getdata():
        # 비슷한 색끼리 묶습니다
        key = (r // 24 * 24, g // 24 * 24, b // 24 * 24)
        counts[key] = counts.get(key, 0) + 1

    best, best_score = None, 0.0
    for (r, g, b), n in counts.items():
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < MIN_SATURATION:
            continue          # 회색·검정·흰색
        if l < 0.12 or l > 0.92:
            continue          # 너무 어둡거나 밝아 색을 알아볼 수 없음
        # 선명함에 큰 가중치를 둡니다. 넓이만 보면 표지의 옅은 배경색이 뽑힙니다.
        # (예: 흰 바탕에 파란 파도 → 파란색이 나와야 하는데 크림색이 나왔었습니다)
        score = n * (s ** 2.5)
        if score > best_score:
            best, best_score = (h, l, s), score

    if best is None:
        return None

    h, l, s = best
    low, high = THEME_LIGHTNESS.get(theme, THEME_LIGHTNESS["밤"])
    l = min(max(l, low), high)
    # 원래 흐린 색을 억지로 진하게 만들지 않습니다. 살짝만 다듬습니다.
    s = min(max(s, 0.5), 0.85)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return _hex(round(r * 255), round(g * 255), round(b * 255))
