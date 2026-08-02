"""설정 파일(config.json)과 비밀키(.env)를 읽어오는 곳."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
CARD_DIR = OUT_DIR / "cards"
DB_PATH = OUT_DIR / "drafts.db"

load_dotenv(ROOT / ".env")


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
