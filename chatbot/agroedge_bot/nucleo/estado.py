"""O pouco que o bot lembra entre reinícios, num arquivo JSON.

- por conversa, só no modo terminal (no Telegram isso fica na plataforma): o cultivo
  escolhido e se quer alertas;
- por cultivo: a data do último fechamento já avisado (para não repetir nem perder
  alertas quando o SSE cai);
- por placa: o último status avisado (online/offline), para avisar só quando muda.

O arquivo é do bot (não vai para o git). Apagar só faz o bot esquecer essas escolhas.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("estado")


@dataclass
class Preferencias:
    cultivo_id: int | None = None
    alertas: bool = True


@dataclass
class Estado:
    conversas: dict[str, Preferencias] = field(default_factory=dict)
    ultimo_diario: dict[str, str] = field(default_factory=dict)  # cultivo_id → AAAA-MM-DD
    status_placa: dict[str, str] = field(default_factory=dict)  # serial → online/offline
    caminho: Path | None = field(default=None, repr=False, compare=False)

    def conversa(self, conversa_id: str) -> Preferencias:
        return self.conversas.setdefault(conversa_id, Preferencias())

    # ------------------------------------------------------------ arquivo

    @classmethod
    def carregar(cls, caminho: str | Path | None) -> Estado:
        if caminho is None:
            return cls()
        caminho = Path(caminho)
        if not caminho.exists():
            return cls(caminho=caminho)
        try:
            dados: dict[str, Any] = json.loads(caminho.read_text(encoding="utf-8"))
            return cls(
                conversas={k: Preferencias(**v) for k, v in dados.get("conversas", {}).items()},
                ultimo_diario=dict(dados.get("ultimo_diario", {})),
                status_placa=dict(dados.get("status_placa", {})),
                caminho=caminho,
            )
        except (ValueError, TypeError) as erro:
            log.warning("estado ilegível em %s (%s): começando do zero", caminho, erro)
            return cls(caminho=caminho)

    def salvar(self) -> None:
        if self.caminho is None:
            return
        dados = {
            "conversas": {k: asdict(v) for k, v in self.conversas.items()},
            "ultimo_diario": self.ultimo_diario,
            "status_placa": self.status_placa,
        }
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporario, self.caminho)  # troca atômica: não corrompe se o bot cair
