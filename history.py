import json
from datetime import datetime
from pathlib import Path
from typing import List

from tutor.utils import get_logger

logger = get_logger(__name__)

HISTORY_DIR = "history"


def _ensure_dir() -> Path:
    path = Path.cwd() / HISTORY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_file() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return _ensure_dir() / f"chat_{today}.jsonl"


def save_entry(question: str, answer: str, sources: List[str]) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "answer": answer,
        "sources": sources,
    }
    path = _session_file()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Errore salvataggio cronologia: %s", e)


def get_recent(n: int = 10) -> List[dict]:
    path = _session_file()
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception as e:
        logger.warning("Errore lettura cronologia: %s", e)
    return entries[-n:]
