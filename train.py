import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from tutor.config import Config
from tutor.ingest import classify_file
from llama_index.llms.ollama import Ollama

from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

QUESTION_TEMPLATES = {
    "SUBROUTINE": [
        "Come si crea una subroutine che {desc}?",
        "Spiega il funzionamento della subroutine {name}",
        "Quali parametri accetta {name}?",
        "Mostra un esempio di subroutine per {desc}",
    ],
    "CLASS_METHOD": [
        "Come si implementa {desc} in una classe?",
        "Spiega il metodo {name} della classe",
        "Quali sono i parametri del metodo {name}?",
        "Mostra un esempio di metodo per {desc}",
    ],
    "QUERY_DEFINITION": [
        "Come si definisce una query per {desc}?",
        "Spiega la struttura della query {name}",
        "Mostra un esempio di definizione query per {desc}",
    ],
    "ADVANCED_QUERY": [
        "Come si usa COMPUTEDCOLUMN in una query?",
        "Spiega l'uso di JOIN nelle query BC",
        "Come si crea una query con colonne calcolate?",
    ],
    "CTE_QUERY": [
        "Come si definisce una CTE in BC?",
        "Spiega le CTE ricorsive in ambiente Sistemi",
        "Mostra un esempio di Common Table Expression",
    ],
    "SUBQUERY": [
        "Come si usa una subquery nella clausola IN?",
        "Spiega le subquery in BC",
        "Mostra un esempio di sottoquery",
    ],
    "QUERY_UPDATE": [
        "Come si aggiornano i dati con UPDATEDBDATA?",
        "Spiega come modificare campi usando una query",
    ],
    "EXERCISE": [
        "Come si risolve l'esercizio {name}?",
        "Spiega il codice dell'esercizio {name}",
        "Qual e' lo scopo dell'esercizio {name}?",
    ],
    "DB_ACCESS": [
        "Come si leggono i dati dal database con GETDBDATA?",
        "Spiega l'accesso ai dati con GETDBDATA",
        "Mostra un esempio di lettura tabella BLDART",
    ],
    "DYNAMIC_STRUCT": [
        "Come si definisce una struttura dinamica?",
        "Spiega come aggiungere elementi a una struttura",
        "Mostra un esempio di DEFDYNSTRUCT e ADDDYNSTRUCT",
    ],
    "VIDEO_DEFINITION": [
        "Come si crea un video in BC?",
        "Spiega i comandi DEFVID, DEFLABEL, DEFEDIT",
        "Mostra come definire un form di input dati",
    ],
    "DATAREADER_EXAMPLE": [
        "Come si usa DataReader per leggere dati?",
        "Spiega DATAREADER con un esempio",
        "Mostra come iterare su un resultset con DataReader",
    ],
    "ENUM_EXAMPLE": [
        "Come si usano gli enumerati (TIPO) in BC?",
        "Spiega Switch/Case con esempi",
        "Mostra l'uso di TIPO e Check() in BC",
    ],
    "DLL_CALL": [
        "Come si chiama una DLL da BC?",
        "Spiega @SBL per chiamate a librerie esterne",
    ],
    "TYPE_EXAMPLE": [
        "Come si usano i TIPO definiti dall'utente?",
        "Spiega la dichiarazione e verifica dei TIPO",
    ],
    "FUNCTION_EXAMPLE": [
        "Come si converte una data in BC?",
        "Spiega GetDayOfWeek con esempio GIORNI",
    ],
    "ALGORITHM_EXAMPLE": [
        "Come si inverte una collezione in BC?",
        "Spiega l'algoritmo di inversione con FOR",
    ],
    "REVIEW_EXAMPLE": [
        "Come si chiama una subroutine esistente?",
        "Spiega come passare parametri tra moduli",
    ],
}

SYSTEM_PROMPT = (
    "Sei un assistente didattico esperto in ambiente SISTEMI e linguaggio BC. "
    "Rispondi SEMPRE in italiano con tono didattico. "
    "Includi il codice BC pertinente spiegandolo passo passo. "
    "Cita sempre la fonte (file .BC) utilizzata."
)

ANSWER_PROMPT = (
    "Sei un insegnante di programmazione ambiente SISTEMI/BC.\n\n"
    "Contesto:\n{context}\n\n"
    "Domanda: {question}\n\n"
    "Rispondi in italiano, cita la fonte, includi codice se presente. Massimo 3 frasi."
)


def _generate_qa_pairs(
    fname: str, content: str, meta: Dict[str, str]
) -> List[Dict]:
    tipo = meta.get("tipo", "OTHER")
    pg_name = meta.get("pg_name", "")
    desc = meta.get("descrizione", "")
    templates = QUESTION_TEMPLATES.get(tipo, [
        "Spiega il seguente codice BC: {name}",
        "Cosa fa il programma {name}?",
    ])

    questions = []
    for tmpl in templates:
        q = tmpl.format(name=pg_name or Path(fname).stem, desc=desc or "operazione")
        questions.append(q)

    qa_pairs = []
    for q in questions[:2]:
        qa_pairs.append({
            "question": q,
            "context": content,
            "file_name": fname,
            "tipo": tipo,
            "categoria": meta.get("categoria", ""),
            "pg_name": pg_name,
        })

    return qa_pairs


def _build_template_answer(item: Dict) -> str:
    tipo = item.get("tipo", "programma")
    pg = item.get("pg_name", "")
    fname = item.get("file_name", "?")
    context = item.get("context", "")
    lines = [l.strip() for l in context.split("\n") if l.strip() and not l.strip().startswith("'")]

    code_lines = [l for l in lines if any(k in l for k in ("@PG", "@SBP", "@SR", "@DEF", "@GET", "@UPDATEDBDATA", "End", "DIM", "CALL", "If", "For", "While", "Switch"))]
    code_sample = "\n".join(code_lines[:10])

    tipo_label = {
        "SUBROUTINE": "subroutine", "CLASS_METHOD": "metodo", "QUERY_DEFINITION": "query",
        "ADVANCED_QUERY": "query avanzata", "CTE_QUERY": "CTE", "SUBQUERY": "sottoquery",
        "QUERY_UPDATE": "query di modifica", "EXERCISE": "esercizio", "DB_ACCESS": "accesso DB",
        "DYNAMIC_STRUCT": "struttura dinamica", "VIDEO_DEFINITION": "video",
        "DATAREADER_EXAMPLE": "DataReader", "ENUM_EXAMPLE": "enumerato",
        "DLL_CALL": "chiamata DLL", "TYPE_EXAMPLE": "TIPO", "FUNCTION_EXAMPLE": "funzione",
        "ALGORITHM_EXAMPLE": "algoritmo", "REVIEW_EXAMPLE": "ripasso",
        "DFX_SCHEMA": "schema tabella", "DFX_METADATA": "metadati DFX", "QUERY_METADATA": "metadati query",
    }.get(tipo, "programma")

    parts = [f"Ecco la spiegazione del file {fname} ({tipo_label}):"]
    if pg:
        parts.append(f"Il programma si chiama {pg}.")
    if code_sample:
        parts.append(f"\nCodice:\n```\n{code_sample}\n```")
    parts.append(f"\nPer approfondire, consulta il file {fname} nella directory docs/bc_file.")
    return "\n".join(parts)


def _generate_answer(llm: Any, question: str, context: str) -> str:
    context_short = context[:1000].strip()
    prompt = ANSWER_PROMPT.format(context=context_short, question=question)
    try:
        resp = llm.complete(prompt)
        return resp.text.strip()
    except Exception as e:
        logger.warning("Errore generazione risposta: %s", e)
        return ""


def _to_openai_format(item: Dict) -> Dict:
    answer = item.get("answer", _build_template_answer(item))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Usando il contesto seguente, rispondi alla domanda.\n\n"
            f"Contesto ({item['file_name']}):\n{item['context'][:2000]}\n\n"
            f"Domanda: {item['question']}"
        )},
        {"role": "assistant", "content": answer},
    ]
    return {"messages": messages}


def run(config: Config) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold yellow]Auto-Allenamento: Generazione Dataset con Risposte[/bold yellow]",
            border_style="yellow",
        )
    )
    console.print()

    llm = Ollama(
        model=config.llm_model,
        base_url=config.ollama_base_url,
        temperature=config.llm_temperature,
        request_timeout=60.0,
    )
    bc_path = Path(config.bc_path)
    output_dir = Path(config.train_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bc_files = sorted(bc_path.glob("*.BC"))
    bc_files = [f for f in bc_files if not any(
        f.name.endswith(e) for e in (".OLD", ".ERR", ".ORIG")
    )]

    if not bc_files:
        console.print("[red]Nessun file BC trovato.[/red]")
        return

    console.print(
        f"[cyan]Generazione dataset da {len(bc_files)} file BC...[/cyan]\n"
        f"[dim]Fase 1: generazione domande | Fase 2: generazione risposte (LLM)[/dim]"
    )
    console.print()

    # Fase 1: Genera domande
    all_qa: List[Dict] = []
    cat_dist: Dict[str, int] = {}

    for bc_path_file in bc_files:
        try:
            content = bc_path_file.read_text("latin-1")
        except Exception:
            continue

        meta = classify_file(bc_path_file.name, content)
        qa_list = _generate_qa_pairs(bc_path_file.name, content, meta)

        for qa in qa_list:
            all_qa.append(qa)

        cat = meta.get("categoria", "altro")
        cat_dist[cat] = cat_dist.get(cat, 0) + len(qa_list)

    random.shuffle(all_qa)
    dataset = all_qa[:config.train_dataset_size]

    console.print(
        f"[green]Fase 1 completata: {len(all_qa)} domande generate, "
        f"{len(dataset)} nel dataset[/green]"
    )

    # Fase 2: Genera risposte con LLM
    answered = 0
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Generazione risposte con LLM...", total=len(dataset)
        )

        for item in dataset:
            answer = _generate_answer(llm, item["question"], item["context"])
            if answer:
                item["answer"] = answer
                answered += 1
            else:
                item["answer"] = (
                    f"Ecco il codice da {item['file_name']}. "
                    f"Analizziamo il funzionamento:\n\n"
                    f"```\n{item['context'][:500]}\n```"
                )
            progress.advance(task)

    # Fase 3: Salva in tutti i formati
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # OpenAI format (messages)
    openai_list = [_to_openai_format(item) for item in dataset if item.get("answer")]
    openai_path = output_dir / f"openai_{timestamp}.jsonl"
    with open(openai_path, "w", encoding="utf-8") as f:
        for entry in openai_list:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ChatML format (istruzione + risposta)
    chatml_path = output_dir / f"chatml_{timestamp}.jsonl"
    with open(chatml_path, "w", encoding="utf-8") as f:
        for item in dataset:
            entry = {
                "instruction": item["question"],
                "input": f"File: {item['file_name']}\nCategoria: {item['categoria']}",
                "output": item.get("answer", ""),
                "file": item["file_name"],
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Riepilogo
    console.print()
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Metrica", style="bold", width=30)
    summary.add_column("Valore")

    summary.add_row("Domande generate", str(len(all_qa)))
    summary.add_row("Dataset selezionato", str(len(dataset)))
    summary.add_row("Risposte generate (LLM)", f"{answered}/{len(dataset)}")
    summary.add_row("File elaborati", str(len(bc_files)))
    summary.add_row("OpenAI format", openai_path.name)
    summary.add_row("ChatML format", chatml_path.name)
    total_cats = sum(cat_dist.values())
    for cat, count in sorted(cat_dist.items()):
        pct = count / total_cats * 100 if total_cats else 0
        summary.add_row(f"  {cat}", f"{count} ({pct:.0f}%)")

    console.print(Panel(summary, title="Riepilogo Dataset", border_style="green"))
    console.print()

    console.print(
        Panel(
            "[green]Dataset completo con risposte![/green]\n\n"
            "Formati disponibili:\n"
            f"  • [bold]OpenAI[/bold] ({openai_path.name}) — per fine-tuning con axolotl, unsloth, litellm, OpenAI API\n"
            f"  • [bold]ChatML[/bold] ({chatml_path.name}) — per Ollama Modelfile, llama.cpp\n\n"
            "Per fare fine-tuning reale:\n"
            "  [dim]Opzione 1[/dim] Ollama: crea un Modelfile che includa i messaggi di esempio\n"
            "  [dim]Opzione 2[/dim] Unsloth: converti il JSONL OpenAI e lancia training\n"
            "  [dim]Opzione 3[/dim] Axolotl: usa direttamente il formato OpenAI JSONL\n\n"
            "Per un test rapido del Modelfile:\n"
            f"  [bold]ollama create mia-istruttore -f {output_dir / 'Modelfile.example'}[/bold]",
            title="Prossimi Passi",
            border_style="yellow",
        )
    )
    console.print()
