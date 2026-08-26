import shutil
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from tutor.config import Config
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()


def run(config: Config) -> None:
    db_path = Path(config.database_path)

    if not db_path.exists():
        console.print("[yellow]- Database vettoriale non presente.[/yellow]")
        return

    if not Confirm.ask(
        "[red]Sei sicuro di voler cancellare il database?[/red]"
    ):
        console.print("[yellow]Operazione annullata.[/yellow]")
        return

    shutil.rmtree(db_path)
    console.print(f"[green]Database cancellato: {db_path.resolve()}[/green]")
