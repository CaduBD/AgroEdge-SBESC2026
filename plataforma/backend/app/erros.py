"""Erro de negócio com código curto e mensagem em pt-BR. Sem dependência de FastAPI.

A API transforma em `{"erro": "codigo_curto", "mensagem": "..."}` (seção 10).
"""


class ErroApp(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


def nao_encontrado(recurso: str = "Recurso") -> ErroApp:
    return ErroApp(404, "nao_encontrado", f"{recurso} não encontrado.")
