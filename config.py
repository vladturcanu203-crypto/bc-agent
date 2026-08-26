import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_FILE_NAME = "config.toml"


@dataclass
class Config:
    llm_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"
    docs_path: str = "docs/pdf"
    bc_path: str = "docs/bc_file"
    database_path: str = "database"
    collection_name: str = "tutor_docs"
    web_search_url: str = "https://bcrif.sistemi.com/"
    chunk_size: int = 768
    chunk_overlap: int = 100
    similarity_top_k: int = 8
    ollama_base_url: str = "http://localhost:11434"
    llm_temperature: float = 0.05
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_k: int = 4
    search_filter: Optional[str] = None
    train_dataset_size: int = 50
    train_output_dir: str = "training_data"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        if path is None:
            path = cls._find_config()
        if path is not None and path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            return cls._from_dict(data)
        return cls()

    @classmethod
    def _find_config(cls) -> Optional[Path]:
        local = Path.cwd() / CONFIG_FILE_NAME
        if local.exists():
            return local
        user = Path.home() / ".config" / "ai-tutor" / CONFIG_FILE_NAME
        if user.exists():
            return user
        return None

    @classmethod
    def _from_dict(cls, data: dict) -> "Config":
        config = cls()

        models = data.get("models", {})
        config.llm_model = models.get("llm", config.llm_model)
        config.embedding_model = models.get("embedding", config.embedding_model)
        config.llm_temperature = models.get("temperature", config.llm_temperature)

        paths = data.get("paths", {})
        config.docs_path = paths.get("docs", config.docs_path)
        config.bc_path = paths.get("bc", config.bc_path)
        config.database_path = paths.get("database", config.database_path)

        rag = data.get("rag", {})
        config.chunk_size = rag.get("chunk_size", config.chunk_size)
        config.chunk_overlap = rag.get("chunk_overlap", config.chunk_overlap)
        config.similarity_top_k = rag.get("similarity_top_k", config.similarity_top_k)

        ollama = data.get("ollama", {})
        config.ollama_base_url = ollama.get("base_url", config.ollama_base_url)

        web = data.get("web", {})
        config.web_search_url = web.get("search_url", config.web_search_url)

        reranker = data.get("reranker", {})
        config.reranker_enabled = reranker.get("enabled", config.reranker_enabled)
        config.reranker_model = reranker.get("model", config.reranker_model)
        config.reranker_top_k = reranker.get("top_k", config.reranker_top_k)

        training = data.get("training", {})
        config.train_dataset_size = training.get("dataset_size", config.train_dataset_size)
        config.train_output_dir = training.get("output_dir", config.train_output_dir)

        return config
