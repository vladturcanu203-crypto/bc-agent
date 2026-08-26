import importlib
from pathlib import Path
from typing import List

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tutor.config import Config
from tutor.models import CheckResult
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()


def check_ollama(config: Config) -> CheckResult:
    try:
        r = httpx.get(f"{config.ollama_base_url}/api/tags", timeout=5.0)
        if r.status_code == 200:
            return CheckResult("Ollama", True, "In esecuzione")
        return CheckResult("Ollama", False, f"Stato: HTTP {r.status_code}")
    except httpx.ConnectError:
        return CheckResult(
            "Ollama", False, "Non raggiungibile. Avvia con: ollama serve"
        )
    except Exception as e:
        return CheckResult("Ollama", False, str(e))


def check_model(config: Config, model: str) -> CheckResult:
    try:
        r = httpx.get(f"{config.ollama_base_url}/api/tags", timeout=5.0)
        if r.status_code != 200:
            return CheckResult(f"Modello {model}", False, "Ollama non disponibile")
        models = r.json().get("models", [])
        installed = any(
            m.get("name") == model or m.get("name", "").startswith(model + ":")
            for m in models
        )
        if installed:
            return CheckResult(f"Modello {model}", True, "Installato")
        return CheckResult(
            f"Modello {model}",
            False,
            f"Non trovato. Esegui: ollama pull {model}",
        )
    except Exception as e:
        return CheckResult(f"Modello {model}", False, str(e))


def check_docs_dir(config: Config) -> CheckResult:
    path = Path(config.docs_path)
    if not path.exists():
        return CheckResult("Directory documenti", False, f"Non trovata: {path}")
    pdfs = list(path.rglob("*.pdf"))
    if not pdfs:
        return CheckResult("Directory documenti", True, "Presente (0 PDF)")
    return CheckResult("Directory documenti", True, f"Presente ({len(pdfs)} PDF)")


def check_bc_dir(config: Config) -> CheckResult:
    path = Path(config.bc_path)
    if not path.exists():
        return CheckResult("Directory BC", False, f"Non trovata: {path}")
    bc_files = list(path.rglob("*.[Bb][Cc]"))
    if not bc_files:
        return CheckResult("Directory BC", True, "Presente (0 file BC)")
    return CheckResult("Directory BC", True, f"Presente ({len(bc_files)} file BC)")


def check_database(config: Config) -> CheckResult:
    path = Path(config.database_path)
    if not path.exists():
        return CheckResult(
            "Database vettoriale", False, "Non trovato. Esegui: tutor ingest"
        )
    return CheckResult("Database vettoriale", True, "Presente")


def check_collection(config: Config) -> CheckResult:
    try:
        import chromadb

        db = chromadb.PersistentClient(path=config.database_path)
        collections = db.list_collections()
        for c in collections:
            if c.name == config.collection_name:
                count = c.count()
                return CheckResult(
                    "Collection Chroma", True, f"Presente ({count} chunk)"
                )
        return CheckResult(
            "Collection Chroma",
            False,
            "Non trovata. Esegui: tutor ingest",
        )
    except Exception as e:
        return CheckResult("Collection Chroma", False, str(e))


def check_dependencies() -> CheckResult:
    required = [
        "llama_index.core",
        "llama_index.embeddings.ollama",
        "llama_index.llms.ollama",
        "llama_index.vector_stores.chroma",
        "chromadb",
        "rich",
        "typer",
        "pypdf",
    ]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return CheckResult(
            "Dipendenze", False, f"Mancanti: {', '.join(missing)}"
        )
    return CheckResult("Dipendenze", True, "OK")


def run(config: Config) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold blue]> AI Tutor - Verifica Ambiente[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    checks: List[CheckResult] = [
        check_ollama(config),
        check_model(config, config.llm_model),
        check_model(config, config.embedding_model),
        check_docs_dir(config),
        check_bc_dir(config),
        check_database(config),
        check_collection(config),
        check_dependencies(),
    ]

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("Check", style="bold", width=35)
    table.add_column("Stato", width=10)
    table.add_column("Dettaglio")

    all_ok = True
    for check in checks:
        if check.ok:
            status = "[green]OK[/green]"
            detail = f"{check.message}"
        else:
            status = "[red]ERR[/red]"
            detail = f"{check.message}"
            all_ok = False
        table.add_row(f"  {check.name}", status, detail)

    console.print(table)
    console.print()

    if all_ok:
        console.print("[bold green]Tutti i controlli superati![/bold green]")
    else:
        console.print(
            "[bold yellow]Alcuni controlli hanno fallito. "
            "Risolvi i problemi sopra.[/bold yellow]"
        )
    console.print()
