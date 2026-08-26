import httpx
import chromadb
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress

from tutor.config import Config
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()


def _get_embedding(text: str, config: Config) -> list:
    url = f"{config.ollama_base_url.rstrip('/')}/api/embeddings"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            json={"model": config.embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


def run(config: Config, keyword: str) -> None:
    console.print()
    console.print(
        Panel.fit(
            f"[bold blue]Ricerca: {keyword}[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    try:
        db = chromadb.PersistentClient(path=config.database_path)
        collection = db.get_collection(config.collection_name)
    except Exception as e:
        console.print(f"[red]Errore database: {e}[/red]")
        console.print("[yellow]Esegui 'tutor ingest' per ricreare il database.[/yellow]")
        return

    with console.status("[cyan]Embedding della query...", spinner="dots"):
        embedding = _get_embedding(keyword, config)

    with Progress() as progress:
        task = progress.add_task("[cyan]Ricerca in corso...", total=None)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=20,
        )
        progress.remove_task(task)

    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]

    if not ids:
        console.print("[yellow]Nessun risultato trovato.[/yellow]")
        return

    table = Table(box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=3)
    table.add_column("Documento", style="cyan", no_wrap=True)
    table.add_column("Tipo", width=16)
    table.add_column("Score", style="green", width=8)
    table.add_column("Anteprima", style="white", max_width=80)

    for i, (doc_id, dist, meta, doc_text) in enumerate(
        zip(ids, distances, metadatas, documents), 1
    ):
        score = f"{1 - dist:.3f}" if dist is not None else "-"
        fname = meta.get("file_name", "?") if meta else "?"
        page = meta.get("page_label", "") if meta else ""

        source_type = meta.get("source_type", "pdf") if meta else "pdf"
        categoria = meta.get("categoria", "") if meta else ""

        fname_str = f"{fname}" + (f" (p.{page})" if page else "")
        preview = (doc_text or "")[:120].replace("\n", " ")

        if source_type == "bc":
            tipo_label = categoria.capitalize() if categoria else "BC"
        else:
            tipo_label = "PDF"

        table.add_row(str(i), fname_str, tipo_label, score, preview)

    console.print(table)
    console.print(f"\n[dim]{len(ids)} risultati trovati[/dim]")
    console.print()
