import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from tutor.config import Config
from tutor.rag import get_query_engine, get_llm
from tutor.webfetch import search_bc_online
from tutor import cache as cache_mod
from tutor import history as history_mod
from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

HELP_TEXT = """
[bold cyan]Comandi disponibili:[/bold cyan]

  [bold]/exit[/bold]              Esci dalla chat
  [bold]/clear[/bold]             Pulisci la console
  [bold]/sources[/bold]          Mostra le fonti dell'ultima risposta
  [bold]/export[/bold]           Salva l'ultima risposta in un file .md
  [bold]/history[/bold]          Mostra le ultime domande della sessione
  [bold]/model <nome>[/bold]     Cambia modello LLM (es. /model llama3.2)
  [bold]/retry[/bold]            Rigenera l'ultima risposta
  [bold]/stats[/bold]            Mostra statistiche del database
  [bold]/cache[/bold]            Mostra il numero di domande in cache
  [bold]/cacheclear[/bold]       Cancella la cache
  [bold]/tipo <categoria>[/bold] Filtra la ricerca per categoria (subroutine, classe, query, esercizio, tipo, esempio)
  [bold]/help[/bold]             Mostra questo aiuto
"""

CATEGORY_LABELS = {
    "subroutine": "Subroutine",
    "classe": "Classe/Metodo",
    "query": "Query",
    "esercizio": "Esercizio",
    "tipo": "Tipo Dato",
    "esempio": "Esempio",
    "ripasso": "Ripasso",
    "datareader": "DataReader",
    "database": "DB Access",
    "struttura": "Struttura Dinamica",
    "video": "Video",
    "dll": "DLL",
    "enumerato": "Enumerato",
    "dfx": "DFX",
    "query_metadata": "Metadati Query",
    "pdf": "Documentazione PDF",
}

CATEGORY_COLORS = {
    "subroutine": "cyan",
    "classe": "magenta",
    "query": "blue",
    "esercizio": "green",
    "tipo": "yellow",
    "esempio": "yellow",
    "ripasso": "dim",
    "datareader": "cyan",
    "database": "cyan",
    "struttura": "magenta",
    "video": "green",
    "dll": "blue",
    "enumerato": "yellow",
    "dfx": "white",
    "query_metadata": "dim",
    "pdf": "white",
}

MAX_HISTORY_TURNS = 4


def _get_category_color(cat: str) -> str:
    return CATEGORY_COLORS.get(cat, "white")


def _get_category_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, cat.capitalize())


def _format_source_type(source_type: str, categoria: str) -> str:
    if source_type == "pdf":
        return "[white]PDF[/white]"
    label = _get_category_label(categoria)
    color = _get_category_color(categoria)
    return f"[{color}]{label}[/{color}]"


def _build_context_prompt(history: List[Dict]) -> str:
    if not history:
        return ""
    parts = ["## Cronologia conversazione recente:"]
    for h in history[-MAX_HISTORY_TURNS:]:
        q = h.get("question", "")
        a = h.get("answer", "")
        a_short = a[:300].replace("\n", " ") if a else ""
        parts.append(f"Domanda: {q}")
        parts.append(f"Risposta: {a_short}")
    parts.append("---")
    return "\n".join(parts)


def _show_help() -> None:
    console.print(HELP_TEXT)


def show_sources(
    response: Any = None,
    web_used: bool = False,
    cached_sources: Optional[List[str]] = None,
) -> None:
    sources: list[Tuple[str, str, str, str, str]] = []

    if response is not None:
        source_nodes = getattr(response, "source_nodes", [])
        seen: Set[Tuple[str, str, str, str]] = set()
        for node_with_score in source_nodes:
            metadata = node_with_score.node.metadata
            fname = metadata.get("file_name", "Sconosciuto")
            page = metadata.get("page_label", "")
            score = getattr(node_with_score, "score", None)
            score_str = f"{score:.3f}" if score is not None else "-"
            source_type = metadata.get("source_type", "pdf")
            categoria = metadata.get("categoria", "")
            stype_display = _format_source_type(source_type, categoria)
            key = (fname, page, score_str, stype_display)
            if key not in seen:
                seen.add(key)
                sources.append((fname, page, score_str, stype_display, source_type))

    if cached_sources:
        for s in cached_sources:
            sources.append((s, "-", "-", "[dim]cache[/dim]", "cache"))

    if not sources and not web_used:
        return

    table = Table(title="Fonti utilizzate", box=None, padding=(0, 1))
    table.add_column("Documento", style="cyan", no_wrap=True)
    table.add_column("Tipo", width=20)
    table.add_column("Pag.", style="dim", width=5, justify="right")
    table.add_column("Score", style="green", width=7, justify="right")

    for fname, page, score, stype_display, _ in sources:
        table.add_row(fname, stype_display, page if page else "-", score)
    if web_used:
        table.add_row("[yellow]Modulo Online: bcrif.sistemi.com[/yellow]", "[yellow]Web[/yellow]", "-", "-")

    console.print()
    console.print(table)
    console.print()


def _extract_source_names(response: Any) -> List[str]:
    seen: Set[str] = set()
    sources = []
    for node_with_score in getattr(response, "source_nodes", []):
        fname = node_with_score.node.metadata.get("file_name", "?")
        if fname not in seen:
            seen.add(fname)
            sources.append(fname)
    return sources


def _answer_with_rag(query_engine: Any, question: str, config: Config, history: Optional[List[Dict]] = None) -> Tuple[str, Any]:
    full_question = question
    if history:
        ctx = _build_context_prompt(history)
        if ctx:
            full_question = f"{ctx}\n\nNuova domanda: {question}"

    response = query_engine.query(full_question)
    text = ""
    try:
        for chunk in response.response_gen:
            text += chunk
    except (AttributeError, TypeError, StopIteration):
        pass
    if not text:
        text = str(response)
    return text, response


def _answer_with_web(query: str, config: Config) -> Optional[str]:
    with console.status("[dim]Consultazione modulo online...", spinner="earth"):
        content = search_bc_online(query, config.web_search_url)
    return content


def _get_suggestions(llm: Any, question: str, answer: str) -> Optional[str]:
    prompt = (
        f"Domanda: {question}\n\n"
        f"Risposta data: {answer}\n\n"
        "Genera 3 domande di approfondimento in italiano per uno studente "
        "che sta imparando l'ambiente Sistemi e il linguaggio BC. "
        "Le domande devono essere pertinenti all'argomento trattato. "
        "Rispondi solo con le 3 domande, una per riga, senza prefissi, numeri o caratteri speciali."
    )
    try:
        resp = llm.complete(prompt)
        return resp.text
    except Exception as e:
        logger.debug("Suggerimenti non generati: %s", e)
        return None


def _rebuild_query_engine(config: Config):
    console.print("[dim]Modello cambiato, ricarico...[/dim]")
    return get_query_engine(config)


def interactive_chat(config: Config) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]AI Tutor - Chat Interattiva[/bold cyan]\n"
            "[dim]Digita /help per i comandi | /exit per uscire[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    try:
        query_engine = get_query_engine(config)
        llm = get_llm(config)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        return
    except Exception as e:
        logger.exception("Errore durante l'avvio della chat")
        console.print(f"[red]Errore: {e}[/red]")
        return

    last_response: Any = None
    last_rag_text: str = ""
    last_web_used = False
    last_question: str = ""
    conversation_history: List[Dict[str, str]] = []
    active_filter: Optional[str] = None

    while True:
        try:
            question = console.input("[bold yellow]Tu >[/bold yellow] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not question:
            continue

        cmd = question.lower()
        if cmd in ("/exit", "exit", "quit", "esci"):
            break
        if cmd in ("/help", "/?"):
            _show_help()
            continue
        if cmd == "/clear":
            console.clear()
            continue
        if cmd == "/sources" and last_response is not None:
            show_sources(last_response, web_used=last_web_used)
            continue
        if cmd == "/export" and last_rag_text:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = Path.cwd() / f"risposta_{ts}.md"
            out.write_text(last_rag_text, encoding="utf-8")
            console.print(f"[green]Risposta salvata in:[/green] {out.name}")
            continue
        if cmd.startswith("/tipo "):
            active_filter = cmd[6:].strip()
            if active_filter:
                valid_filters = list(CATEGORY_LABELS.keys())
                if active_filter in valid_filters:
                    console.print(f"[green]Filtro attivo:[/green] {_get_category_label(active_filter)}")
                else:
                    console.print(f"[yellow]Filtro '{active_filter}' non riconosciuto. Filtri validi: {', '.join(valid_filters)}[/yellow]")
                    active_filter = None
            else:
                active_filter = None
                console.print("[green]Filtro rimosso.[/green]")
            continue
        if cmd == "/retry" and last_question:
            question = last_question
            console.print(f"[dim]Rigenero risposta per:[/dim] {question}")
            console.print()
        if cmd.startswith("/model "):
            new_model = cmd[7:].strip()
            if new_model:
                config.llm_model = new_model
                try:
                    query_engine = _rebuild_query_engine(config)
                    llm = get_llm(config)
                    console.print(f"[green]Modello cambiato a:[/green] {new_model}")
                except Exception as e:
                    console.print(f"[red]Errore: {e}[/red]")
            continue
        if cmd == "/history":
            recent = history_mod.get_recent(5)
            if not recent:
                console.print("[dim]Nessuna cronologia.[/dim]")
            else:
                for e in recent:
                    t = e["timestamp"][11:19]
                    q = e["question"][:80]
                    console.print(f"  [dim]{t}[/dim] {q}")
            continue
        if cmd == "/stats":
            from tutor import stats as stats_mod
            stats_mod.run(config)
            continue
        if cmd == "/cache":
            data = cache_mod._load()
            console.print(f"[cyan]Domande in cache:[/cyan] {len(data)}")
            continue
        if cmd == "/cacheclear":
            cache_mod.clear()
            console.print("[green]Cache cancellata.[/green]")
            continue

        console.print()

        full_question = question
        if active_filter:
            full_question = f"[Categoria: {active_filter}] {question}"

        cached = cache_mod.lookup(full_question)
        if cached:
            answer, source = cached
            last_rag_text = answer
            last_question = question
            console.print(Markdown(answer))
            console.print()
            if cached_sources := cache_mod.get_sources(full_question):
                show_sources(cached_sources=cached_sources)
            else:
                console.print("[dim]Risposta dalla cache[/dim]")
            console.print()
            conversation_history.append({"question": question, "answer": answer})
            continue

        start = time.time()

        with console.status("[cyan]Cerco nella documentazione...", spinner="dots"):
            try:
                rag_text, response = _answer_with_rag(
                    query_engine, full_question, config, conversation_history
                )
            except Exception as e:
                logger.exception("Errore durante la query")
                console.print(f"[red]Errore: {e}[/red]")
                continue

        elapsed = time.time() - start
        last_response = response
        last_rag_text = rag_text
        last_question = question

        web_used = False
        is_not_found = "non e' presente nella documentazione" in rag_text.lower()

        if is_not_found:
            web_content = _answer_with_web(question, config)
            if web_content:
                web_used = True
                rag_text = (
                    f"{rag_text}\n\n---\n"
                    f"**Modulo Online (bcrif.sistemi.com):**\n{web_content}"
                )
                elapsed = time.time() - start

        last_web_used = web_used

        try:
            with Live(
                Markdown(""),
                refresh_per_second=15,
                console=console,
            ) as live:
                live.update(Markdown(rag_text))
        except Exception as e:
            logger.exception("Errore durante la generazione")
            console.print(f"[red]Errore durante la generazione: {e}[/red]")

        source_names = _extract_source_names(response)
        if web_used:
            source_names.append("Modulo Online: bcrif.sistemi.com")
        cache_mod.store(full_question, rag_text, source_names)
        history_mod.save_entry(question, rag_text, source_names)
        conversation_history.append({"question": question, "answer": rag_text})

        console.print()
        console.print(f"[dim]Tempo: {elapsed:.1f}s[/dim]")
        show_sources(response, web_used=web_used)

        with console.status("[dim]Genero suggerimenti...", spinner="dots"):
            suggestions = _get_suggestions(llm, question, rag_text)
        if suggestions:
            lines = [l.strip().strip('"').strip("•").strip("- ") for l in suggestions.strip().split("\n") if l.strip()]
            if lines:
                console.print("[bold magenta]Potresti chiedere:[/bold magenta]")
                for s in lines[:3]:
                    s_clean = s.lstrip("123. ").strip()
                    console.print(f"  [dim]•[/dim] [italic]{s_clean}[/italic]")
                console.print()

        console.print()


def _handle_command(question: str) -> bool:
    cmd = question.strip().lower()
    if cmd in ("/help", "/?"):
        _show_help()
        return True
    if cmd == "/cacheclear":
        cache_mod.clear()
        console.print("[green]Cache cancellata.[/green]")
        return True
    if cmd == "/clear":
        console.clear()
        return True
    if cmd.startswith("/"):
        console.print(f"[yellow]Comando '{cmd}' non disponibile in modalità singola.[/yellow]")
        return True
    return False


def single_question(config: Config, question: str) -> None:
    if _handle_command(question):
        return

    try:
        query_engine = get_query_engine(config)
        llm = get_llm(config)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        return
    except Exception as e:
        logger.exception("Errore durante l'avvio")
        console.print(f"[red]Errore: {e}[/red]")
        return

    console.print()
    console.print(f"[bold yellow]Domanda:[/bold yellow] {question}")
    console.print()

    cached = cache_mod.lookup(question)
    if cached:
        answer, source = cached
        console.print(Markdown(answer))
        console.print()
        if cached_sources := cache_mod.get_sources(question):
            show_sources(cached_sources=cached_sources)
        else:
            console.print("[dim]Risposta dalla cache[/dim]")
        console.print()
        return

    start = time.time()

    with console.status("[cyan]Cerco nella documentazione...", spinner="dots"):
        try:
            rag_text, response = _answer_with_rag(query_engine, question, config)
        except Exception as e:
            logger.exception("Errore durante la query")
            console.print(f"[red]Errore: {e}[/red]")
            return

    elapsed = time.time() - start

    web_used = False
    is_not_found = "non e' presente nella documentazione" in rag_text.lower()

    if is_not_found:
        web_content = _answer_with_web(question, config)
        if web_content:
            web_used = True
            rag_text = (
                f"{rag_text}\n\n---\n"
                f"**Modulo Online (bcrif.sistemi.com):**\n{web_content}"
            )
            elapsed = time.time() - start

    try:
        with Live(
            Markdown(""),
            refresh_per_second=15,
            console=console,
        ) as live:
            live.update(Markdown(rag_text))
    except Exception as e:
        logger.exception("Errore durante la generazione")
        console.print(f"[red]Errore durante la generazione: {e}[/red]")

    source_names = _extract_source_names(response)
    if web_used:
        source_names.append("Modulo Online: bcrif.sistemi.com")
    cache_mod.store(question, rag_text, source_names)
    history_mod.save_entry(question, rag_text, source_names)

    console.print()
    console.print(f"[dim]Tempo: {elapsed:.1f}s[/dim]")
    show_sources(response, web_used=web_used)

    with console.status("[dim]Genero suggerimenti...", spinner="dots"):
        suggestions = _get_suggestions(llm, question, rag_text)
    if suggestions:
        lines = [l.strip().strip('"').strip("•").strip("- ") for l in suggestions.strip().split("\n") if l.strip()]
        if lines:
            console.print("[bold magenta]Potresti chiedere:[/bold magenta]")
            for s in lines[:3]:
                s_clean = s.lstrip("123. ").strip()
                console.print(f"  [dim]•[/dim] [italic]{s_clean}[/italic]")
            console.print()
