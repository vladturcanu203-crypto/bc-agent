from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tutor.config import Config
from tutor.ingest import classify_file
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

CATEGORY_LABELS = {
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
    "dfx": "[white]DFX[/white]",
    "query_metadata": "[dim]METADATI[/dim]",
    "errore": "[red]ERR[/red]",
    "altro": "[dim]ALTRO[/dim]",
}


def run(config: Config) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold green]Esercizi BC e Documenti Disponibili[/bold green]",
            border_style="green",
        )
    )
    console.print()

    bc_path = Path(config.bc_path)
    if not bc_path.exists():
        console.print(f"[yellow]Directory non trovata: {bc_path}[/yellow]")
        return

    all_files = sorted(bc_path.iterdir())
    bc_files = [f for f in all_files if f.suffix.upper() == ".BC"]
    mod_files = [f for f in all_files if f.suffix.upper() == ".MOD"]
    dfx_files = [f for f in all_files if f.suffix.upper() in (".DFX", ".DFY")]
    sxdfx_files = [f for f in all_files if f.suffix.upper() == ".SXDFX"]
    sxmdqry_files = [f for f in all_files if f.suffix.upper() == ".SXMDQRY"]
    other = [f for f in all_files if f.suffix.upper() not in
             (".BC", ".MOD", ".OLD", ".ERR", ".ORIG", ".DFX", ".DFY", ".SXDFX", ".SXMDQRY")]

    table = Table(box=None, padding=(0, 2))
    table.add_column("Tipo", style="bold", width=22)
    table.add_column("Conteggio", justify="right", width=10)
    table.add_column("Dettaglio")

    table.add_row("Esercizi (.BC)", str(len(bc_files)), "File sorgente principali")
    table.add_row("  Subroutine", "", "SUB_*, SUB0*")
    table.add_row("  Classi/Metodi", "", "BLD_*, CLS*, CLIENTI*")
    table.add_row("  Query", "", "QUERY_*, @PGQUERY, CTE, Subquery")
    table.add_row("  Corso Base", "", "CBAS_*")
    table.add_row("Schemi (.DFX/.DFY)", str(len(dfx_files)), "Definizione tabella")
    table.add_row("Metadati (.SXDFX)", str(len(sxdfx_files)), "XML struttura dati")
    table.add_row("Metadati Query (.SXMDQRY)", str(len(sxmdqry_files)), "XML metadati query")
    table.add_row("Modifiche (.MOD)", str(len(mod_files)), "Versioni modificate")
    table.add_row("Altri formati", str(len(other)), "Query output, etc.")
    table.add_row(
        "[bold]Totale[/bold]",
        f"[bold]{len(bc_files) + len(mod_files) + len(dfx_files) + len(sxdfx_files) + len(sxmdqry_files) + len(other)}[/bold]",
        "Esclusi backup (.OLD, .ERR, .ORIG)",
    )

    console.print(table)
    console.print()

    if bc_files:
        console.print("[bold]Esercizi disponibili (.BC):[/bold]")

        for f in bc_files:
            try:
                content = f.read_text("latin-1")
            except Exception:
                continue
            meta = classify_file(f.name, content)
            label = CATEGORY_LABELS.get(meta["categoria"], "[dim]ALTRO[/dim]")
            desc = meta.get("descrizione", "")
            desc_str = f" - [italic]{desc}[/italic]" if desc else ""
            console.print(f"  {label} {f.name}{desc_str}")

        console.print()

    docs_path = Path(config.docs_path)
    if docs_path.exists():
        pdfs = sorted(docs_path.rglob("*.pdf"))
        console.print(f"[bold]Documenti PDF:[/bold] {len(pdfs)}")
        for p in pdfs:
            console.print(f"  - {p.name}")
        console.print()
