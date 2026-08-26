from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from tutor.config import Config
from tutor.ingest import classify_file, _format_file_text
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

CATEGORY_LABELS = {
    "subroutine": "Subroutine", "classe": "Classe/Metodo", "query": "Query",
    "esercizio": "Esercizio", "tipo": "Tipo Dato", "esempio": "Esempio",
    "ripasso": "Ripasso", "datareader": "DataReader", "database": "DB Access",
    "struttura": "Struttura Dinamica", "video": "Video", "dll": "DLL",
    "enumerato": "Enumerato", "dfx": "DFX", "query_metadata": "Metadati Query",
}


def run(config: Config, filename: str) -> None:
    bc_path = Path(config.bc_path)

    target = filename.upper()
    if not target.endswith(".BC"):
        target += ".BC"

    found = None
    for f in bc_path.iterdir():
        if f.is_file() and f.name.upper() == target:
            found = f
            break

    if not found:
        for f in bc_path.iterdir():
            if f.is_file() and f.name.upper().startswith(target):
                found = f
                break

    if not found:
        console.print(f"[red]File non trovato: {filename}[/red]")
        return

    try:
        content = found.read_text("latin-1")
    except Exception:
        console.print(f"[red]Errore lettura file: {found}[/red]")
        return

    meta = classify_file(found.name, content)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]{found.name}[/bold cyan]",
            border_style="cyan",
        )
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Proprietà", style="bold", width=20)
    table.add_column("Valore")

    table.add_row("Nome programma", meta.get("pg_name") or "-")
    table.add_row("Tipo", CATEGORY_LABELS.get(meta["categoria"], meta["categoria"]))
    table.add_row("Categoria", meta["tipo"])
    table.add_row("Descrizione", meta.get("descrizione") or "-")
    table.add_row("Percorso", str(found))

    console.print(table)
    console.print()

    syntax = Syntax(content, "vbnet", theme="monokai", line_numbers=True, word_wrap=True)
    console.print(Panel(syntax, border_style="green"))
    console.print()
