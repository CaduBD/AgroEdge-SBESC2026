"""Limite de tentativas de login (contra quem tenta adivinhar a senha).

Conta as falhas numa janela deslizante, por IP e por e-mail. Passou do limite, o login
responde 429 até a falha mais antiga sair da janela. Fica em memória: o app roda num só
processo (Uvicorn sem workers), e reiniciar zera a contagem, o que é aceitável.

O limite por e-mail é maior que o por IP: sem isso, alguém de fora bloquearia o login do
dono só errando a senha dele de propósito.
"""

import time
from collections import deque
from collections.abc import Callable, Iterable

MAX_CHAVES = 10_000  # teto de memória: acima disso, limpa as chaves sem falhas recentes


class LimiteLogin:
    def __init__(
        self,
        max_falhas: int,
        janela_s: float,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_falhas = max_falhas
        self.janela_s = janela_s
        self.relogio = relogio
        self._falhas: dict[str, deque[float]] = {}

    def _recentes(self, chave: str, agora: float) -> deque[float]:
        fila = self._falhas.get(chave)
        if fila is None:
            return deque()
        while fila and agora - fila[0] >= self.janela_s:
            fila.popleft()
        if not fila:
            del self._falhas[chave]
        return fila

    def espera_s(self, chaves: Iterable[tuple[str, int]]) -> float:
        """Segundos até poder tentar de novo (0 = liberado). `chaves`: (chave, limite)."""
        agora = self.relogio()
        espera = 0.0
        for chave, limite in chaves:
            fila = self._recentes(chave, agora)
            if len(fila) >= limite:
                espera = max(espera, fila[0] + self.janela_s - agora)
        return espera

    def falhou(self, chaves: Iterable[str]) -> None:
        agora = self.relogio()
        if len(self._falhas) > MAX_CHAVES:
            for chave in list(self._falhas):
                self._recentes(chave, agora)
        for chave in chaves:
            self._falhas.setdefault(chave, deque()).append(agora)

    def acertou(self, chaves: Iterable[str]) -> None:
        for chave in chaves:
            self._falhas.pop(chave, None)

    def limpar(self) -> None:
        self._falhas.clear()
