import sys
from typing import Optional

import typer
from rich.console import Console

from tutor import __version__
from tutor.config import Config
from tutor.utils import setup_logging

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

console = Console()

app = typer.Typer(
    name="tutor",
    help="AI Tutor - Assistente didattico locale con RAG",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Abilita log dettagliati",
    ),
) -> None:
    setup_logging(level=10 if verbose else 20)


@app.command()
def ingest() -> None:
    """Indicizza i documenti PDF e file BC presenti in docs/"""
    config = Config.load()
    from tutor import ingest as ingest_mod

    ingest_mod.run(config)


@app.command()
def update() -> None:
    """Reindicizza i documenti (elimina e ricrea il database)"""
    config = Config.load()
    import shutil
    from pathlib import Path
    db_path = Path(config.database_path)
    if db_path.exists():
        shutil.rmtree(db_path)
    console.print("[yellow]Database ricreato da zero.[/yellow]")
    from tutor import ingest as ingest_mod
    ingest_mod.run(config)


@app.command()
def ask(
    question: Optional[str] = typer.Argument(
        None,
        help="Domanda da porre al tutor (ometti per chat interattiva)",
    ),
    tipo: Optional[str] = typer.Option(
        None,
        "--tipo",
        "-t",
        help="Filtra per categoria: subroutine, classe, query, esercizio, tipo, esempio",
    ),
) -> None:
    """Pone una domanda al tutor o avvia una chat interattiva"""
    config = Config.load()

    if tipo:
        config.search_filter = tipo

    from tutor import chat as chat_mod

    if question:
        chat_mod.single_question(config, question)
    else:
        chat_mod.interactive_chat(config)


@app.command()
def stats() -> None:
    """Mostra statistiche del database vettoriale"""
    config = Config.load()
    from tutor import stats as stats_mod

    stats_mod.run(config)


@app.command()
def doctor() -> None:
    """Verifica lo stato dell'ambiente (Ollama, modelli, dipendenze)"""
    config = Config.load()
    from tutor import doctor as doctor_mod

    doctor_mod.run(config)


@app.command()
def search(
    keyword: str = typer.Argument(
        ..., help="Parola chiave da cercare nei documenti"
    ),
) -> None:
    """Cerca keyword nei documenti indicizzati (full-text veloce)"""
    config = Config.load()
    from tutor import search as search_mod

    search_mod.run(config, keyword)


@app.command()
def learn() -> None:
    """Mostra l'elenco degli esercizi BC disponibili"""
    config = Config.load()
    from tutor import learn as learn_mod

    learn_mod.run(config)


@app.command()
def show(
    filename: str = typer.Argument(
        ..., help="Nome del file BC da visualizzare (es. SUB_SOMMA.BC)"
    ),
) -> None:
    """Mostra il contenuto di un file BC con metadati"""
    config = Config.load()
    from tutor import display as display_mod

    display_mod.run(config, filename)


@app.command()
def debug(
    filename: Optional[str] = typer.Argument(
        None,
        help="Nome del file .ERR da analizzare (ometti per elencare tutti gli errori)",
    ),
) -> None:
    """Analizza errori di compilazione (.ERR) e li spiega in italiano"""
    config = Config.load()
    from tutor import debug as debug_mod

    debug_mod.run(config, filename)


@app.command()
def train() -> None:
    """Auto-allenamento: genera dataset di training da esercizi e risposte"""
    config = Config.load()
    from tutor import train as train_mod

    train_mod.run(config)


@app.command()
def clear() -> None:
    """Cancella completamente il database vettoriale"""
    config = Config.load()
    from tutor import clear as clear_mod

    clear_mod.run(config)


@app.command()
def version() -> None:
    """Mostra la versione del programma"""
    console.print(f"[bold cyan]AI Tutor v{__version__}[/bold cyan]")


if __name__ == "__main__":
    app()
