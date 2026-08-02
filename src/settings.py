"""설정 파일(config.json)과 비밀키(.env)를 읽어오는 곳."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
CARD_DIR = OUT_DIR / "cards"
DB_PATH = OUT_DIR / "drafts.db"

# .env 는 내 컴퓨터에서만 씁니다.
# GitHub Actions 에서는 Secrets 가 환경변수로 들어오므로 dotenv 가 없어도 됩니다.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    pass


def load_config() -> dict:
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def env(name: str, required: bool = False) -> str:
    value = (os.environ.get(name) or "").strip()
    if required and not value:
        raise RuntimeError(
            f"{name} 값이 비어 있습니다. book-bot 폴더의 .env 파일을 열어 채워주세요."
        )
    return value


def ensure_dirs() -> None:
    CARD_DIR.mkdir(parents=True, exist_ok=True)
