"""Catálogo de culturas (espelho do firmware/modelo/culturas.py, apêndice A)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ARQUIVO = Path(__file__).with_name("culturas.json")


@lru_cache
def culturas() -> list[dict[str, Any]]:
    return json.loads(_ARQUIVO.read_text(encoding="utf-8"))


def cultura(chave: str) -> dict[str, Any] | None:
    return next((c for c in culturas() if c["chave"] == chave), None)
