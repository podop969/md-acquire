from __future__ import annotations

from ..config import Config
from .arxiv import ArxivAdapter
from .base import Adapter
from .gutenberg import GutenbergAdapter
from .openlibrary import OpenLibraryAdapter
from .unpaywall import UnpaywallAdapter

CLASSES = {
    "arxiv": ArxivAdapter,
    "openlibrary": OpenLibraryAdapter,
    "gutenberg": GutenbergAdapter,
    "unpaywall": UnpaywallAdapter,
}


def build(names: list[str], cfg: Config) -> list[Adapter]:
    return [CLASSES[n](cfg) for n in names if n in CLASSES]