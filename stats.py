from pathlib import Path

import chromadb
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tutor.config import Config
from tutor.utils import get_logger, get_database_size

logger = get_logger(__name__)
console = Console()


def run(config: Config) -> None:
    db_path = Path(config.database_path)

    if not db_path.exists():
        console.print("[yellow]Database vettoriale non trovato.[/yellow]")
        console.print("[yellow]  Esegui 'tutor ingest' per crearlo.[/yellow]")
        return

    try:
        db = chromadb.PersistentClient(path=str(db_path))
        collection = db.get_collection(config.collection_name)
    except Exception:
        console.print("[red]Collection Chroma non trovata.[/red]")
        console.print("[yellow]  Esegui 'tutor ingest' per ricrearla.[/yellow]")
        return

    result = collection.get()
    num_chunks = len(result["ids"])

    unique_files: set = set()
    for meta in result["metadatas"]:
        if meta and "file_name" in meta:
            unique_files.add(str(meta["file_name"]))

    db_size = get_database_size(db_path)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metrica", style="bold", width=25)
    table.add_column("Valore")

    table.add_row("Documenti", str(len(unique_files)))
    table.add_row("Chunk", str(num_chunks))
    table.add_row("Modello embedding", config.embedding_model)
    table.add_row("Modello LLM", config.llm_model)
    table.add_row("Dimensione database", db_size)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Statistiche Database Vettoriale[/bold blue]",
            border_style="blue",
        )
    )
    console.print()
    console.print(table)
    console.print()
