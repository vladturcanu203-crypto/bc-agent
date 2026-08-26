from dataclasses import dataclass
from typing import Optional


@dataclass
class Source:
    file_name: str
    page_label: Optional[str] = None
    text: Optional[str] = None
    score: Optional[float] = None


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str = ""


@dataclass
class Stats:
    num_documents: int = 0
    num_chunks: int = 0
    embedding_model: str = ""
    llm_model: str = ""
    database_size: str = ""
    last_indexed: Optional[str] = None
