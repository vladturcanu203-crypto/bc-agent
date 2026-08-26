from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from tutor.config import Config
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()


def _parse_err_file(content: str) -> list:
    errors = []
    current = {}

    for line in content.split("\n"):
        line_stripped = line.strip()

        if not line_stripped:
            continue

        if ".BC - Linea" in line_stripped and "Colonna" in line_stripped:
            current = {"raw": line_stripped, "context": ""}
            errors.append(current)

            parts = line_stripped.split(" - ")
            if len(parts) >= 2:
                loc_part = parts[0]
                loc_parts = loc_part.split(" - ")
                if len(loc_parts) >= 2:
                    loc = loc_parts[0].strip()
                    current["location"] = loc
            current["message"] = line_stripped

        elif current and line_stripped.startswith("["):
            if "message" in current:
                current["message"] += "\n" + line_stripped
            current["context"] = line_stripped

        elif current and not line_stripped.startswith("[") and not line_stripped.startswith("Traduttore") and not line_stripped.startswith("Errori/Warnings") and not line_stripped.startswith("***"):
            if "context" in current and current["context"]:
                current["message"] = current.get("message", "") + "\n" + line_stripped

        if "message" in current and ("Linea" in line_stripped and "Colonna" in line_stripped):
            if current.get("message") and current["message"] != line_stripped:
                pass

    return errors


def _explain_error(err_msg: str) -> str:
    err_upper = err_msg.upper()

    explanations = []

    if "#1144" in err_upper:
        explanations.append("**Compatibilità .NET**: La subroutine richiamata non è valida per .NET. "
                           "Verifica che sia marcata come compatibile.")
    elif "#10356" in err_upper:
        explanations.append("**Richiamo @SBL non consentito**: Non puoi chiamare una subroutine con @SBL "
                           "quando l'oggetto AGIS è presente nello stesso prodotto. Usa CALL o @SRP.")
    elif "WARNING" in err_upper:
        explanations.append("**Warning (non bloccante)**: Il codice verrà tradotto ma il warning "
                           "suggerisce una potenziale incompatibilità o una pratica da migliorare.")
    elif "ERRORE" in err_upper or "ERROR" in err_upper:
        explanations.append("**Errore di compilazione**: Il codice non può essere tradotto. "
                           "Controlla la sintassi nella linea indicata.")

    if not explanations:
        explanations.append("**Errore generico**: Consulta la documentazione per la sintassi corretta.")

    return "\n".join(explanations)


def run(config: Config, filename: Optional[str] = None) -> None:
    bc_path = Path(config.bc_path)

    err_files = sorted(bc_path.glob("*.ERR"))
    if not err_files:
        console.print("[yellow]Nessun file .ERR trovato.[/yellow]")
        return

    if filename:
        target = filename.upper()
        if not target.endswith(".ERR"):
            target += ".ERR"
        err_files = [f for f in err_files if f.name.upper() == target]
        if not err_files:
            err_files = [f for f in err_files if target in f.name.upper()]

    console.print()
    console.print(
        Panel.fit(
            "[bold red]Analisi Errori di Compilazione[/bold red]",
            border_style="red",
        )
    )
    console.print()

    total_errors = 0
    for err_path in err_files:
        try:
            content = err_path.read_text("latin-1")
        except Exception:
            continue

        errors = _parse_err_file(content)
        if not errors:
            continue

        total_errors += len(errors)

        console.print(f"[bold cyan]{err_path.name}[/bold cyan]")
        for err in errors[:3]:
            loc = err.get("location", err.get("raw", "?"))

            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("", style="bold", width=12)
            table.add_column("")

            table.add_row("Posizione", loc)
            table.add_row("Spiegazione", _explain_error(err.get("message", "")))

            console.print(table)
            console.print()
            break

        if len(errors) > 1:
            console.print(f"[dim]... e {len(errors) - 1} errore/i in più[/dim]")
            console.print()

    if total_errors == 0:
        console.print("[green]Nessun errore trovato nei file .ERR selezionati.[/green]")

    if not filename and err_files:
        console.print(f"[dim]File con errori: {len(err_files)} | Errori totali: {total_errors}[/dim]")
