# AgroEdge - leitura do anemômetro de conchas Met One 014A (cabo/ligação Campbell Scientific).
# MicroPython (BitDogLab / RP2040).
#
# Dentro dele há uma chave reed selada: as conchas giram um ímã que abre e fecha o contato a
# uma taxa proporcional ao vento. É contato seco (não precisa de alimentação) e não há
# protocolo digital: conta-se os pulsos por segundo (f, em Hz) e converte pela calibração
# de fábrica:  v (m/s) = ANEMO_M × f + ANEMO_B = 0,8 × f + 0,447   (v = 0 se f = 0).
# Faixa 0-45 m/s, partida 0,45 m/s, precisão 1,5% ou 0,11 m/s. A 45 m/s, f ≈ 56 Hz
# (~18 ms entre pulsos), então o debounce de 2 ms não perde pulso.
#
# Ligação oficial (pino cfg.PINO_ANEMOMETRO = GPIO18, 1º pino da fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V"):
#   3V3 ──[10 kΩ]──┐
#   fio do sensor ─┴──[1 kΩ]──┬── GPIO18
#                          [100 nF]
#   outro fio ──── GND ───────┘
#   O 10 kΩ é o pull-up forte (cabo longo pega menos ruído); 1 kΩ + 100 nF é um filtro RC
#   (~0,1 ms) que segura picos sem atrasar o pulso. No cabo Campbell original o PRETO é o
#   sinal; se o cabo não for original, ache o par com o multímetro (ver LEIA-ME_ANEMOMETRO.md).
#   O pull-up interno é ligado sempre: com o externo não atrapalha, e sem os componentes
#   (teste de bancada: um fio no GPIO18 e o outro no GND) é ele que segura o pino em 1.
#
# Uso:
#   a = anemometro.Anemometro()     # começa a contar (carrega a média do dia salva, se houver)
#   n, f, v = a.ler(1.0)            # pulsos, Hz e m/s numa janela de 1 s (bloqueia 1 s)
#   n, f, v = a.medir()             # o mesmo, mas desde a última chamada (não bloqueia)
#   a.adicionar(v, dt)              # soma na média do dia (a média é ponderada pelo tempo)
#   a.salvar()                      # de vez em quando (ex.: a cada 10 min), não a cada amostra
#   u2, rajada, n = a.fechar_dia()  # no fim do dia: média do vento a 2 m (m/s) para o ET0 e
#                                   # para historico.fechar_dia(..., vento=u2, ...), e zera
#
# O "vento" do modelo é a média diária a 2 m de altura em m/s (Velocidade_Vento do
# DataClimaBR), por isso a média do dia já sai convertida para 2 m (FAO-56, eq. 47).
# A rajada é o maior valor de uma janela de medir()/ler() (1 s em amostrar()), na altura
# do sensor, sem conversão.

import json
import math
import time
import config_local as cfg

try:
    import machine
    from machine import Pin
except ImportError:          # permite testar as contas no PC
    machine = Pin = None

try:
    import micropython
    micropython.alloc_emergency_exception_buf(100)   # mostra o erro se a IRQ falhar
except (ImportError, AttributeError):
    pass

MAIOR_INT = 0x3FFFFFFF       # maior inteiro "pequeno" do MicroPython (não aloca memória)


# ------------------------------------------------------------ contas (testáveis no PC)

def velocidade(f, m=None, b=None):
    """m/s a partir da frequência f (Hz). Parado (f = 0) é 0, não 0,447."""
    if f <= 0:
        return 0.0
    m = cfg.ANEMO_M if m is None else m
    b = cfg.ANEMO_B if b is None else b
    return m * f + b


def frequencia(pulsos, segundos):
    """Pulsos por segundo (Hz) numa janela."""
    return pulsos / segundos if segundos > 0 else 0.0


def para_2m(uz, z=None):
    """Vento a 2 m a partir do medido na altura z (m), FAO-56 eq. 47 (perfil logarítmico
    sobre grama): u2 = uz × 4,87 / ln(67,8 z − 5,42)."""
    z = cfg.ANEMO_ALTURA_M if z is None else z
    if abs(z - 2.0) < 1e-6:
        return uz
    return uz * 4.87 / math.log(67.8 * z - 5.42)


def km_h(v):
    return v * 3.6


# ------------------------------------------------------------ sensor (só na placa)

class Anemometro:
    # arquivo=None: só conta, não grava na flash (usado no teste). A anotação entre aspas é só
    # para o Pylance; o MicroPython ignora anotações.
    def __init__(self, pino=None, arquivo: "str | None" = "vento_hoje.json", debounce_ms=None):
        if Pin is None:
            raise OSError("Anemometro precisa da placa (machine); no PC use só as funções")
        self.pino_n = cfg.PINO_ANEMOMETRO if pino is None else pino
        self.arquivo = arquivo
        self.debounce_us = int(1000 * (cfg.ANEMO_DEBOUNCE_MS if debounce_ms is None
                                       else debounce_ms))
        # estado da interrupção: só inteiros pequenos, para o handler não alocar memória
        self._pulsos = 0          # aceitos desde o último medir() (zerado lá)
        self._rejeitados = 0      # bordas a menos de debounce da anterior aceita (repique/ruído)
        self._ultimo_us = time.ticks_us()
        self._ultima_borda_us = self._ultimo_us
        self._menor_borda_us = MAIOR_INT   # menor intervalo entre duas bordas quaisquer
        self._menor_ok_us = MAIOR_INT      # menor intervalo entre dois pulsos aceitos
        # fora da interrupção
        self.total = 0
        self.rejeitados_total = 0
        self._t_ant = time.ticks_us()
        self.ultimo_dt = 0.0
        self.ultimos_rejeitados = 0
        # média do dia (vento a 2 m ponderado pelo tempo) e rajada
        self.soma = 0.0           # Σ u2 × dt  (m/s × s)
        self.tempo = 0.0          # Σ dt (s)
        self.n = 0
        self.rajada = 0.0
        self._n_salvo = 0
        if arquivo:
            try:
                with open(arquivo) as f:
                    e = json.load(f)
                self.soma, self.tempo = e["soma"], e["tempo"]
                self.n, self.rajada = e["n"], e["rajada"]
                self._n_salvo = self.n
            except (OSError, ValueError, KeyError):
                pass                     # primeiro uso ou arquivo estragado: começa do zero
        self.pino = Pin(self.pino_n, Pin.IN, Pin.PULL_UP)
        try:
            self.pino.irq(trigger=Pin.IRQ_FALLING, handler=self._borda, hard=True)
        except TypeError:                # porta sem IRQ "hard": usa a normal
            self.pino.irq(trigger=Pin.IRQ_FALLING, handler=self._borda)

    def _borda(self, pino):
        """Interrupção: cada fechamento da reed. Só inteiros pequenos, nada de float/print."""
        agora = time.ticks_us()
        d = time.ticks_diff(agora, self._ultima_borda_us)
        if 0 <= d < self._menor_borda_us:
            self._menor_borda_us = d
        self._ultima_borda_us = agora
        d = time.ticks_diff(agora, self._ultimo_us)
        # d < 0: o ticks_us deu a volta (> ~9 min parado), então é pulso novo
        if d < 0 or d >= self.debounce_us:
            if 0 <= d < self._menor_ok_us:
                self._menor_ok_us = d
            self._pulsos += 1
            self._ultimo_us = agora
        else:
            self._rejeitados += 1

    def medir(self):
        """(pulsos, f Hz, v m/s) desde a última chamada. Não bloqueia."""
        estado = machine.disable_irq()   # lê e zera junto, sem perder pulso no meio
        p = self._pulsos
        r = self._rejeitados
        self._pulsos = 0
        self._rejeitados = 0
        machine.enable_irq(estado)
        agora = time.ticks_us()
        dt = time.ticks_diff(agora, self._t_ant) / 1e6
        self._t_ant = agora
        self.total += p
        self.rejeitados_total += r
        self.ultimo_dt = dt
        self.ultimos_rejeitados = r
        f = frequencia(p, dt)
        return p, f, velocidade(f)

    def ler(self, janela_s=1.0):
        """(pulsos, f Hz, v m/s) numa janela de janela_s segundos (bloqueia esse tempo)."""
        self.medir()                     # descarta o que veio antes
        time.sleep_ms(int(janela_s * 1000))
        return self.medir()

    def adicionar(self, v, dt=1.0):
        """Soma uma medida v (m/s, na altura do sensor) de duração dt (s) na média do dia."""
        self.soma += para_2m(v) * dt
        self.tempo += dt
        self.n += 1
        if v > self.rajada:
            self.rajada = v

    def amostrar(self, janela_s=1.0):
        """Mede uma janela, soma no dia e devolve (v, u2)."""
        _, _, v = self.ler(janela_s)
        self.adicionar(v, self.ultimo_dt)
        return v, para_2m(v)

    def media_u2(self):
        """Média do vento a 2 m desde o último fechar_dia (m/s), ou None sem amostras."""
        return self.soma / self.tempo if self.tempo > 0 else None

    def diagnostico(self):
        """(menor intervalo entre bordas, menor entre pulsos aceitos) em ms; None se não houve."""
        a, b = self._menor_borda_us, self._menor_ok_us
        return (None if a == MAIOR_INT else a / 1000, None if b == MAIOR_INT else b / 1000)

    def zerar_diagnostico(self):
        estado = machine.disable_irq()
        self._menor_borda_us = self._menor_ok_us = MAIOR_INT
        machine.enable_irq(estado)
        self.total = self.rejeitados_total = 0

    def salvar(self):
        """Grava a média do dia na flash, só se mudou (a flash gasta com escritas demais)."""
        if self.arquivo and self.n != self._n_salvo:
            with open(self.arquivo, "w") as f:
                json.dump({"soma": self.soma, "tempo": self.tempo, "n": self.n,
                           "rajada": self.rajada}, f)
            self._n_salvo = self.n

    def fechar_dia(self):
        """Devolve (média do vento a 2 m em m/s, rajada em m/s, nº de amostras) e recomeça.
        Sem amostras no dia, a média sai None (decida no main o que usar)."""
        r = (self.media_u2(), self.rajada, self.n)
        self.soma = self.tempo = self.rajada = 0.0
        self.n = 0
        self._n_salvo = -1               # força gravar o dia zerado
        self.salvar()
        return r


# ------------------------------------------------------------ testes

def _testar_contas():
    """Confere as conversões (roda no PC: python3 anemometro.py)."""
    def perto(a, b, tol=1e-6):
        return abs(a - b) <= tol
    falhas = 0
    casos = [
        ("f=0 -> 0 m/s (parado não é 0,447)", velocidade(0), 0.0, 1e-9),
        ("f=10 -> 8,447 m/s", velocidade(10, 0.8, 0.447), 8.447, 1e-9),
        ("f=55,7 -> ~45 m/s", velocidade(55.7, 0.8, 0.447), 45.0, 0.05),
        ("frequencia(25 pulsos, 5 s) = 5 Hz", frequencia(25, 5.0), 5.0, 1e-9),
        ("frequencia(janela 0) = 0", frequencia(3, 0), 0.0, 1e-9),
        ("u2 com z=2 igual a uz", para_2m(5.0, 2.0), 5.0, 1e-12),
        ("u2 com z=10 (FAO-56 ex. 14: 3,2 -> 2,4)", para_2m(3.2, 10.0), 2.393, 0.01),
        ("km/h de 10 m/s = 36", km_h(10.0), 36.0, 1e-9),
    ]
    for nome, obtido, esperado, tol in casos:
        ok = perto(obtido, esperado, tol)
        falhas += not ok
        print("%s  %-42s obtido %.4f  esperado %.4f" % ("OK  " if ok else "FALHA", nome,
                                                       obtido, esperado))
    menor = para_2m(5.0, 3.0) < 5.0
    falhas += not menor
    print("%s  %-42s obtido %.4f  (< 5)" % ("OK  " if menor else "FALHA",
                                           "u2 com z=3 menor que uz", para_2m(5.0, 3.0)))
    print("\n%d falha(s)" % falhas if falhas else "\nTodos os testes passaram.")
    return falhas


if __name__ == "__main__":
    if machine is None:
        import sys
        sys.exit(1 if _testar_contas() else 0)
    # teste rápido na placa (o completo é o teste_anemometro.py): gire as conchas
    a = Anemometro(arquivo=None)
    print("anemômetro no GPIO%d - gire as conchas. Ctrl+C para parar." % a.pino_n)
    while True:
        n, f, v = a.ler(1.0)
        print("pulsos: %3d  f: %5.2f Hz  v: %5.2f m/s  u2: %5.2f m/s" % (n, f, v, para_2m(v)))
