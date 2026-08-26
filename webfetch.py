from typing import Optional

import httpx
from rich.console import Console

from tutor.utils import get_logger

logger = get_logger(__name__)
console = Console()

MAX_LENGTH = 12000


def _try_fetch(client: httpx.Client, url: str) -> Optional[str]:
    try:
        resp = client.get(url, timeout=10.0)
        if resp.status_code == 200:
            text = resp.text
            if len(text) > MAX_LENGTH:
                text = text[:MAX_LENGTH] + "\n\n[--- troncato ---]"
            return text
    except Exception:
        pass
    return None


def search_bc_online(query: str, search_url: str) -> Optional[str]:
    logger.info("Consultazione modulo online: %s", search_url)

    base = search_url.rstrip("/")
    results = []

    urls_to_try = [
        f"{base}/search?q={query}",
        f"{base}/cerca?q={query}",
        f"{base}/?q={query}",
        base,
    ]

    with httpx.Client(follow_redirects=True) as client:
        for url in urls_to_try:
            content = _try_fetch(client, url)
            if content:
                results.append(f"Fonte: {url}\n\n{content}")
                break

    if not results:
        logger.warning("Modulo online: nessuna risposta")
        return None

    return "\n\n---\n\n".join(results)
