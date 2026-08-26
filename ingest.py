import re
import time
from pathlib import Path
from typing import Dict, List

import chromadb
from llama_index.core import (
    Document,
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from rich.console import Console
from rich.panel import Panel

from tutor.config import Config
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

BC_EXTENSIONS = [".BC", ".SXDFX", ".DFX", ".DFY", ".SXMDQRY"]
TEXT_EXTENSIONS = [".BC"]
META_EXTENSIONS = [".SXDFX", ".DFX", ".DFY", ".SXMDQRY"]


def _extract_pg_description(content: str) -> str:
    match = re.search(
        r"@PG(?:QUERY)?\s+\S+\s+STRICT\[\d+\][ \t]*'([^'\n]*)",
        content,
    )
    if match:
        return match.group(1).strip().strip("'").strip()
    return ""


def _extract_pg_name(content: str) -> str:
    match = re.search(r"@PG(?:QUERY)?\s+(\S+)", content)
    if match:
        return match.group(1)
    return ""


def classify_file(filename: str, content: str) -> Dict[str, str]:
    stem = Path(filename).stem.upper()
    ext = Path(filename).suffix.upper()
    lower_content = content.strip()
    pg_name = _extract_pg_name(content)
    descrizione = _extract_pg_description(content)

    tipo = "OTHER"
    categoria = "altro"

    # File metadati (non BC)
    if ext == ".SXDFX":
        tipo = "DFX_METADATA"
        categoria = "dfx"
    elif ext == ".DFX":
        tipo = "DFX_SCHEMA"
        categoria = "dfx"
    elif ext == ".DFY":
        tipo = "DFX_INDEX"
        categoria = "dfx"
    elif ext == ".SXMDQRY":
        tipo = "QUERY_METADATA"
        categoria = "query_metadata"
    elif ext == ".ERR":
        tipo = "COMPILE_ERROR"
        categoria = "errore"
    else:
        has_pgquery = bool(re.search(r"@PGQUERY", lower_content))
        has_defquery = bool(re.search(r"@DEFQUERY", lower_content))
        has_sbp_query = bool(re.search(r"@SBP\s+Query", content))
        has_sbp_class = bool(re.search(r"@SBP\s+This\[CLASSE\[", content))
        has_sbp_tipo = bool(re.search(r"@SBP\s+This\[TIPO\[", content))
        has_sbp_sub = bool(re.search(r"@SBP\s+\w+\[(?:INT|STRING|DATE)\]", content))
        has_sbp_empty = bool(re.search(r"^@SBP\s*$", content, re.MULTILINE))
        has_datareader = bool(re.search(r"DATAREADER\[", content))
        has_updatedb = bool(re.search(r"@UPDATEDBDATA", content))
        has_getdb = bool(re.search(r"@GETDBDATA", content))
        has_defdyn = bool(re.search(r"@DEFDYNSTRUCT|@ADDDYNSTRUCT", content))
        has_defvid = bool(re.search(r"@DEFVID", content))
        has_sbl = bool(re.search(r"@SBL\s", content))
        has_defquerycte = bool(re.search(r"@DEFQUERYCTE", content))
        has_defsubquery = bool(re.search(r"@DEFSUBQUERY", content))
        has_switch = bool(re.search(r"\bSwitch\b", content, re.IGNORECASE))
        has_computed = bool(re.search(r"@COMPUTEDCOLUMN", content))
        has_join = bool(re.search(r"@JOIN\s+TABELLA", content))
        has_orderby = bool(re.search(r"@ORDERBY", content))
        has_sr = bool(re.search(r"@SR\s", content))
        has_enum = bool(re.search(r"TIPO\[\w+\].*=\s*\w+\.\w+", content))
        has_tipo_keyword = bool(re.search(r"\bTIPO\[", content))

        if has_pgquery or has_defquery or has_sbp_query:
            if has_defquerycte:
                tipo = "CTE_QUERY"
                categoria = "query"
            elif has_defsubquery:
                tipo = "SUBQUERY"
                categoria = "query"
            elif has_computed or has_join:
                tipo = "ADVANCED_QUERY"
                categoria = "query"
            else:
                tipo = "QUERY_DEFINITION"
                categoria = "query"
        elif has_updatedb:
            tipo = "QUERY_UPDATE"
            categoria = "query"
        elif has_getdb:
            tipo = "DB_ACCESS"
            categoria = "database"
        elif has_defdyn:
            tipo = "DYNAMIC_STRUCT"
            categoria = "struttura"
        elif has_defvid:
            tipo = "VIDEO_DEFINITION"
            categoria = "video"
        elif has_sbl:
            tipo = "DLL_CALL"
            categoria = "dll"
        elif has_enum or has_switch:
            tipo = "ENUM_EXAMPLE"
            categoria = "enumerato"
        elif has_sbp_class:
            tipo = "CLASS_METHOD"
            categoria = "classe"
        elif has_sbp_tipo:
            tipo = "TYPE_METHOD"
            categoria = "tipo"
        elif stem.startswith("SUB_") or stem.startswith("SUB0"):
            tipo = "SUBROUTINE"
            categoria = "subroutine"
        elif stem.startswith("BLD_TD_"):
            tipo = "TYPE_DEFINITION"
            categoria = "tipo"
        elif stem.startswith("BLD_") or stem.startswith("BLD"):
            tipo = "CLASS_METHOD"
            categoria = "classe"
        elif stem.startswith("CLS"):
            tipo = "CLASS_METHOD"
            categoria = "classe"
        elif stem.startswith("QUERY"):
            tipo = "QUERY"
            categoria = "query"
        elif stem.startswith("ESER") or stem.startswith("ESERC") or stem.startswith("CBAS"):
            tipo = "EXERCISE"
            categoria = "esercizio"
        elif stem in ("FRUTTA_CHECK", "TIPO_FRU"):
            tipo = "TYPE_EXAMPLE"
            categoria = "tipo"
        elif stem == "GIORNI":
            tipo = "FUNCTION_EXAMPLE"
            categoria = "esempio"
        elif stem.startswith("INVERTI"):
            tipo = "ALGORITHM_EXAMPLE"
            categoria = "esempio"
        elif stem.startswith("RIPASSO"):
            tipo = "REVIEW_EXAMPLE"
            categoria = "ripasso"
        elif stem == "DATAREAD":
            tipo = "DATAREADER_EXAMPLE"
            categoria = "datareader"
        elif has_datareader:
            tipo = "DATAREADER_EXAMPLE"
            categoria = "datareader"
        elif has_sbp_sub or has_sbp_empty or has_sr:
            tipo = "SUBROUTINE"
            categoria = "subroutine"

    # Fallback per file BC riconosciuti dal contenuto ma non dal nome
    if tipo == "OTHER" and categoria == "altro":
        if has_enum or has_switch or has_tipo_keyword:
            tipo = "ENUM_EXAMPLE"
            categoria = "enumerato"
        elif has_defdyn:
            tipo = "DYNAMIC_STRUCT"
            categoria = "struttura"
        elif has_defvid:
            tipo = "VIDEO_DEFINITION"
            categoria = "video"
        elif has_getdb:
            tipo = "DB_ACCESS"
            categoria = "database"
        elif has_sbl:
            tipo = "DLL_CALL"
            categoria = "dll"
        elif has_sbp_empty or has_sr:
            tipo = "SUBROUTINE"
            categoria = "subroutine"

    return {
        "tipo": tipo,
        "categoria": categoria,
        "descrizione": descrizione,
        "pg_name": pg_name,
    }


def _format_file_text(fname: str, content: str, meta: Dict[str, str]) -> str:
    parts = [f"[File: {fname}]"]
    if meta.get("pg_name"):
        parts.append(f"[Programma: {meta['pg_name']}]")
    if meta.get("tipo"):
        parts.append(f"[Tipo: {meta['tipo']}]")
    if meta.get("categoria"):
        parts.append(f"[Categoria: {meta['categoria']}]")
    if meta.get("descrizione"):
        parts.append(f"[Descrizione: {meta['descrizione']}]")
    parts.append("")
    parts.append(content)
    return "\n".join(parts)


def load_pdf_documents(docs_path: Path) -> List[Document]:
    if not docs_path.exists():
        return []

    console.print("[bold cyan]Lettura documenti PDF...[/bold cyan]")
    pdf_documents = SimpleDirectoryReader(
        input_dir=str(docs_path.resolve()),
        recursive=True,
        required_exts=[".pdf"],
    ).load_data()

    enriched: List[Document] = []
    if pdf_documents:
        unique_pdf = set()
        for doc in pdf_documents:
            fname = doc.metadata.get("file_name", "?")
            unique_pdf.add(fname)
            new_meta = dict(doc.metadata)
            new_meta["source_type"] = "pdf"
            enriched.append(Document(text=doc.text, metadata=new_meta))

        console.print(
            f"[green]{len(enriched)} pagine da "
            f"{len(unique_pdf)} documenti PDF lette[/green]"
        )
        for fname in sorted(unique_pdf):
            console.print(f"  - {fname}")

    return enriched


def load_text_files(text_path: Path) -> List[Document]:
    if not text_path.exists():
        return []

    console.print("[bold cyan]Lettura file sorgente...[/bold cyan]")

    raw_documents = SimpleDirectoryReader(
        input_dir=str(text_path.resolve()),
        recursive=False,
        required_exts=TEXT_EXTENSIONS,
        exclude=["*.OLD", "*.ERR", "*.ORIG", "*.MOD"],
    ).load_data()

    enriched: List[Document] = []
    cats: Dict[str, int] = {}

    for doc in raw_documents:
        fname = doc.metadata.get("file_name", "?")
        content = doc.text

        file_meta = classify_file(fname, content)
        enriched_text = _format_file_text(fname, content, file_meta)

        new_meta = dict(doc.metadata)
        new_meta["tipo"] = file_meta["tipo"]
        new_meta["categoria"] = file_meta["categoria"]
        new_meta["descrizione"] = file_meta["descrizione"]
        new_meta["pg_name"] = file_meta["pg_name"]
        new_meta["source_type"] = "bc"
        new_meta["file_name"] = fname

        enriched.append(Document(text=enriched_text, metadata=new_meta))

        cat = file_meta["categoria"]
        cats[cat] = cats.get(cat, 0) + 1

    if enriched:
        total = len(enriched)
        console.print(f"[green]{total} documenti letti[/green]")
        label_map = {
            "subroutine": "[cyan]SUB[/cyan]",
            "classe": "[magenta]CLASSE[/magenta]",
            "query": "[blue]QUERY[/blue]",
            "esercizio": "[green]ESERCIZIO[/green]",
            "tipo": "[yellow]TIPO[/yellow]",
            "esempio": "[yellow]ESEMPIO[/yellow]",
            "ripasso": "[dim]RIPASSO[/dim]",
            "datareader": "[cyan]DATAREADER[/cyan]",
            "database": "[cyan]DB_ACCESS[/cyan]",
            "struttura": "[magenta]STRUTTURA[/magenta]",
            "video": "[green]VIDEO[/green]",
            "dll": "[blue]DLL[/blue]",
            "enumerato": "[yellow]ENUM[/yellow]",
            "query_metadata": "[dim]QRY_META[/dim]",
            "dfx": "[white]DFX[/white]",
            "errore": "[red]ERR[/red]",
        }
        for cat, count in sorted(cats.items()):
            label = label_map.get(cat, f"[dim]{cat}[/dim]")
            console.print(f"  {label} {cat}: {count}")

    return enriched


def load_meta_files(meta_path: Path) -> List[Document]:
    if not meta_path.exists():
        return []

    console.print("[bold cyan]Lettura file metadati (DFX/SXDFX/SXMDQRY)...[/bold cyan]")

    raw_documents = SimpleDirectoryReader(
        input_dir=str(meta_path.resolve()),
        recursive=False,
        required_exts=META_EXTENSIONS,
        exclude=["*.OLD", "*.ERR", "*.ORIG"],
    ).load_data()

    enriched: List[Document] = []
    cats: Dict[str, int] = {}

    for doc in raw_documents:
        fname = doc.metadata.get("file_name", "?")
        ext = Path(fname).suffix.lower()
        content = doc.text

        source_type_map = {".sxdfx": "sxdfx", ".dfx": "dfx", ".dfy": "dfy", ".sxmdqry": "sxmdqry"}
        source_type = source_type_map.get(ext, "meta")

        file_meta = classify_file(fname, content)
        enriched_text = _format_file_text(fname, content, file_meta)

        new_meta = dict(doc.metadata)
        new_meta["tipo"] = file_meta["tipo"]
        new_meta["categoria"] = file_meta["categoria"]
        new_meta["descrizione"] = file_meta["descrizione"]
        new_meta["source_type"] = source_type
        new_meta["file_name"] = fname

        enriched.append(Document(text=enriched_text, metadata=new_meta))

        cat = file_meta["categoria"]
        cats[cat] = cats.get(cat, 0) + 1

    if enriched:
        total = len(enriched)
        console.print(f"[green]{total} file metadati letti[/green]")
        for cat, count in sorted(cats.items()):
            console.print(f"  [dim]{cat}[/dim]: {count}")

    return enriched


def run(config: Config) -> None:
    start_time = time.time()
    docs_path = Path(config.docs_path)
    bc_path = Path(config.bc_path)

    pdf_documents = load_pdf_documents(docs_path)
    bc_documents = load_text_files(bc_path)
    meta_documents = load_meta_files(bc_path)
    all_documents = pdf_documents + bc_documents + meta_documents

    if not all_documents:
        console.print("[red]Nessun documento trovato.[/red]")
        return

    pdf_file_count = len(set(
        d.metadata.get("file_name", "?") for d in pdf_documents
    ))
    bc_file_count = len(set(
        d.metadata.get("file_name", "?") for d in bc_documents
    ))
    meta_file_count = len(set(
        d.metadata.get("file_name", "?") for d in meta_documents
    ))

    db_path = Path(config.database_path)
    db_path.mkdir(parents=True, exist_ok=True)

    db = chromadb.PersistentClient(path=str(db_path))
    chroma_collection = db.get_or_create_collection(config.collection_name)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    embed_model = OllamaEmbedding(
        model_name=config.embedding_model,
        base_url=config.ollama_base_url,
    )

    Settings.embed_model = embed_model

    splitter = SentenceSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )

    pdf_ids = {id(d) for d in pdf_documents}
    meta_ids = {id(d) for d in meta_documents}

    all_nodes = []
    for doc in all_documents:
        if id(doc) in pdf_ids or id(doc) in meta_ids:
            all_nodes.extend(splitter.get_nodes_from_documents([doc]))
        else:
            all_nodes.append(
                TextNode(text=doc.text, metadata=dict(doc.metadata))
            )

    with console.status(
        "[cyan]Creazione embedding e salvataggio...", spinner="dots"
    ):
        VectorStoreIndex(
            nodes=all_nodes,
            storage_context=storage_context,
            embed_model=embed_model,
            show_progress=False,
        )

    elapsed = time.time() - start_time
    num_chunks = chroma_collection.count()

    console.print()
    console.print(
        Panel(
            f"[bold green]Indicizzazione completata![/bold green]\n\n"
            f"Documenti PDF: {pdf_file_count}\n"
            f"File BC: {bc_file_count}\n"
            f"Metadati: {meta_file_count}\n"
            f"Segmenti totali: {len(all_nodes)}\n"
            f"Chunk vettoriali: {num_chunks}\n"
            f"Tempo: {elapsed:.1f}s\n"
            f"Database: {db_path.resolve()}",
            title="Riepilogo",
            border_style="green",
        )
    )
    console.print()
