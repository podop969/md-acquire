from __future__ import annotations
from abc import ABC, abstractmethod

from ..config import Config
from ..http import Client
from ..models import Candidate, WorkSpec


class Adapter(ABC):
    """Open-access source. lookup() returns download candidates; it must never
    return links the pipeline is not allowed to fetch automatically."""

    name: str = "base"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    @abstractmethod
    def lookup(self, client: Client, spec: WorkSpec) -> list[Candidate]:
        ...