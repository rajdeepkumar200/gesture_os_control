"""Local file-system + web search."""
from __future__ import annotations

import logging
import os
import webbrowser
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class SearchController:
    """Performs basic local + web searches."""

    DEFAULT_ROOTS = ("Desktop", "Documents", "Downloads")

    def __init__(self, search_roots: List[str] | None = None, max_results: int = 25):
        if search_roots is None:
            home = Path.home()
            search_roots = [str(home / r) for r in self.DEFAULT_ROOTS]
        self.search_roots = [Path(p) for p in search_roots if Path(p).exists()]
        self.max_results = max_results

    # ----------------------------------------------------------- local
    def search_local(self, query: str) -> List[Path]:
        """Case-insensitive substring search across configured roots."""
        if not query:
            return []
        q = query.lower()
        results: List[Path] = []
        for root in self.search_roots:
            try:
                for dirpath, dirnames, filenames in os.walk(root):
                    for name in dirnames + filenames:
                        if q in name.lower():
                            results.append(Path(dirpath) / name)
                            if len(results) >= self.max_results:
                                return results
            except OSError:
                logger.debug("search walk failed in %s", root, exc_info=True)
        return results

    # ----------------------------------------------------------- web
    @staticmethod
    def search_web(query: str, engine: str = "google") -> None:
        if not query:
            return
        engines = {
            "google": "https://www.google.com/search?q={}",
            "bing": "https://www.bing.com/search?q={}",
            "duckduckgo": "https://duckduckgo.com/?q={}",
        }
        url = engines.get(engine, engines["google"]).format(quote_plus(query))
        webbrowser.open(url, new=2, autoraise=True)
        logger.info("Web search opened: %s", url)
