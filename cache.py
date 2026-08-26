import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tutor.utils import get_logger

logger = get_logger(__name__)

CACHE_FILE = "cache_qa.json"
MAX_ENTRIES = 200


def _cache_path() -> Path:
    return Path.cwd() / CACHE_FILE


def _load() -> dict:
    path = _cache_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Errore lettura cache: %s", e)
    return {}


def _save(data: dict) -> None:
    path = _cache_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Errore scrittura cache: %s", e)


def lookup(question: str) -> Optional[Tuple[str, str]]:
    data = _load()
    entry = data.get(question.strip().lower())
    if entry and isinstance(entry, dict):
        answer = entry.get("answer", "")
        if answer:
            logger.info("Cache hit: %s", question[:60])
            return (answer, "cache")
    if entry and isinstance(entry, str):
        logger.info("Cache hit (old format): %s", question[:60])
        return (entry, "cache")
    return None


def get_sources(question: str) -> Optional[List[str]]:
    data = _load()
    entry = data.get(question.strip().lower())
    if entry and isinstance(entry, dict):
        return entry.get("sources", [])
    return None


def store(question: str, answer: str, sources: Optional[List[str]] = None) -> None:
    key = question.strip().lower()
    data = _load()
    data[key] = {
        "answer": answer,
        "sources": sources or [],
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    if len(data) > MAX_ENTRIES:
        oldest = sorted(data.keys())[:50]
        for k in oldest:
            del data[k]
    _save(data)


def clear() -> None:
    path = _cache_path()
    if path.exists():
        path.unlink()
        logger.info("Cache eliminata")
