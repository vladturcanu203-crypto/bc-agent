from typing import Any, List, Optional

import chromadb
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from rich.console import Console

from tutor.config import Config
from tutor.prompts import get_system_prompt
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()


def get_query_engine(config: Config):
    embed_model = OllamaEmbedding(
        model_name=config.embedding_model,
        base_url=config.ollama_base_url,
    )

    llm = Ollama(
        model=config.llm_model,
        base_url=config.ollama_base_url,
        temperature=config.llm_temperature,
        request_timeout=300.0,
        system_prompt=get_system_prompt(),
        additional_kwargs={"num_ctx": 4096, "num_predict": 512},
    )

    Settings.embed_model = embed_model
    Settings.llm = llm

    try:
        db = chromadb.PersistentClient(path=config.database_path)
        chroma_collection = db.get_collection(config.collection_name)
    except Exception:
        logger.error("Database vettoriale non trovato")
        raise RuntimeError(
            "Database vettoriale non trovato. "
            "Esegui 'tutor ingest' per indicizzare i documenti."
        )

    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    index = VectorStoreIndex.from_vector_store(
        vector_store,
        embed_model=embed_model,
    )

    node_postprocessors: List[Any] = [SimilarityPostprocessor(similarity_cutoff=0.3)]

    if config.reranker_enabled:
        try:
            from llama_index.core.postprocessor import SentenceTransformerRerank
            reranker = SentenceTransformerRerank(
                model=config.reranker_model,
                top_n=config.reranker_top_k,
            )
            node_postprocessors.append(reranker)
            logger.info("Reranker attivato: %s", config.reranker_model)
        except ImportError:
            logger.warning(
                "Reranker non disponibile. "
                "Installa: sentence-transformers"
            )
            console.print(
                "[yellow]Reranker abilitato ma non installato. "
                "Procedo senza.[/yellow]"
            )

    query_engine = index.as_query_engine(
        llm=llm,
        similarity_top_k=config.similarity_top_k,
        node_postprocessors=node_postprocessors or None,
        response_mode="compact",
        streaming=True,
    )

    return query_engine


def get_llm(config: Config):
    return Ollama(
        model=config.llm_model,
        base_url=config.ollama_base_url,
        temperature=config.llm_temperature,
        request_timeout=120.0,
    )
