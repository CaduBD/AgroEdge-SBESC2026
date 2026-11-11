# AgroEdge — estação completa (`main.py`)

O `main.py` lê todos os sensores, fecha o dia à meia-noite (hora local) e calcula:
ET0 (Penman-Monteith FAO-56) → ETc = Kc × ET0 → balanço hídrico → classificador → lâmina de irrigação.
Mostra os valores no display da BitDogLab e grava um resumo por dia em `diario.csv` na placa.

## Pinos

| Sensor | Pino | Onde |
|---|---|---|
| DHT22 (T e UR) | GPIO18 | IDC, fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V", 1º pino; VCC no 3V3 |
| Piranômetro RS-485 | UART1 GPIO8 (TX→DI), GPIO9 (RX←RO, divisor 1k/2k), GPIO4 (DE+RE) | mesma fileira; sensor em 12 V |
| Anemômetro Met One 014A | GPIO17 | IDC, fileira "GND GP16 GP17 GND GP28 3V3 GND" |
| Pluviômetro | GPIO16 | mesma fileira do GP17 |
| Relógio DS3231 (opcional) | I²C0: SDA GPIO0, SCL GPIO1, endereço 0x68 | conector I²C0; 3V3 |
| Display OLED | I²C1 GPIO14/15 | o da própria placa |

Livres ainda: GPIO19 e GPIO20.

## Arquivos para copiar para a placa
`main.py`, `config_local.py`, `culturas.py`, `eto.py`, `termohigro.py`, `relogio.py`, `anemometro.py`, `pluviometro.py`,
`piranometro.py`, `historico.py`, `lamina.py`, `classificador.py`, `agroedge_pesos.py`, `ssd1306.py`.
Não copie `__pycache__`, `teste_main_pc.py` nem a pasta `bancada`.

## Antes de ligar no campo (`config_local.py`)
- `LATITUDE` e `ALTITUDE_M` do pomar (o GPS do celular dá os dois).
- `ANEMO_ALTURA_M`: altura real das conchas.
- Cultura (`CULTURA`: `uva_italia` ou `manga_tommy_atkins`) e `DATA_REFERENCIA` (data da poda para a uva, do início
  da floração para a manga). Os dados de cada cultura (Kc, p, raiz e fontes) estão em `culturas.py`.
- Solo (`AGUA_DISP`), `EFICIENCIA`, `AREA_M2`, `VAZAO_L_H`. `RAIZ_M` e `P_LOCAL` só se houver medida no pomar.
- Hora: com DS3231, acerte uma vez pelo Thonny: `import relogio; relogio.acertar(2026, 11, 11, 14, 30)`.
  Com Wi-Fi, preencha `WIFI_SSID`/`WIFI_SENHA` (acerta sozinho pelo NTP e também acerta o DS3231).
  Sem nenhum dos dois, a hora se perde quando a energia cai.

## Testes
- No PC (já passam): `python3 eto.py` (exemplo 18 do FAO-56), `python3 teste_main_pc.py` (109 dias de
  Petrolina), `python3 relogio.py`, `python3 termohigro.py`, e `python3 ../../modelo/05_validar_eto.py`
  (ET0 do firmware × DataClimaBR, 3.651 dias: RMSE 0,07 mm/dia, R² 0,999).
- Na placa, um por vez: `termohigro.py` (mostra T e UR), `relogio.py` (mostra a fonte da hora),
  `teste_anemometro.py`, `bancada/teste_piranometro_rs485.py`, `pluviometro.py`.
- Tudo junto sem esperar a meia-noite: `import main; main.rodar(fechar_agora=True)`.

## Teste de campo de 1 dia (modo 24 h)
No `config_local.py`: `MODO_FECHAMENTO = "24h"` e, se não houver DS3231 nem Wi-Fi, `DATA_INSTALACAO = (2026, 11, 20)`
(a data em que vão ligar). O dia fecha 24 horas de funcionamento depois de ligar: instalando às 10h, às 10h do dia
seguinte o resultado já está no display e no `diario.csv`, com um ciclo de sol completo. Depois disso, a placa
continua fechando uma janela de 24 h a cada 24 h. O tempo desligado (queda de energia) não conta.
Para uso normal, volte para `MODO_FECHAMENTO = "meia_noite"`.

## No dia a dia
- Irrigação aplicada: o sistema não mede. Registre a lâmina líquida do dia pelo Thonny:
  `import main; main.registrar_irrigacao(12.5)` e rode o `main.py` de novo. Sem registro, conta 0 mm.
- O display alterna entre "agora" (T, UR, sol, vento, chuva) e "ontem": ET0; quanto a planta gastou (ETc em
  litros por planta); a classe; quanto irrigar (mm, litros por planta e minutos de válvula); e o total da área
  em m³ (se `N_PLANTAS` estiver no `config_local`).

## Litros de água
1 mm de água sobre 1 m² = 1 litro. Por isso:
- **Gasto do dia** (`consumo_l_planta` no diário) = ETc (mm) × área da planta (`AREA_M2`). É o que a planta consumiu.
- **A aplicar** (`aplicar_l_planta`) = lâmina bruta (mm) × `AREA_M2`. Só quando a classe pede irrigação; repõe o
  déficit acumulado do solo (descontada a chuva) e já inclui as perdas (÷ `EFICIENCIA`).
- **Total da área** (`consumo_l_total`, `aplicar_l_total`) = litros por planta × `N_PLANTAS`.
- Exemplo (manga 8 × 5 m = 40 m², ET0 6 mm, Kc 0,83): gasto de 4,98 mm = 199 L por planta; com 250 plantas
  (1 ha), 49,8 m³ por dia. A irrigação não repõe isso todo dia: o solo guarda água, e o sistema só manda irrigar
  quando o déficit passa do limite da classe.

## Limites conhecidos
- **Dia incompleto:** o primeiro dia (placa ligada no meio do dia) e dias com menos de 80% de leituras
  aparecem no diário, mas não entram no histórico nem no classificador.
- **Dados faltando:** sem vento, usa 2 m/s; sem radiação, estima pela amplitude térmica (ambos do FAO-56).
  Sem T/UR, o dia não tem ET0.
- **Anemômetro desligado:** sem pulsos, o vento é lido como 0 m/s, e não como "faltando". Confira o diário.
- **Classificador:** precisa de 28 dias de histórico e do ciclo desde a poda. Começando no meio do ciclo,
  as primeiras semanas saem com o aviso "classe pouco confiável". Hoje o modelo é o da uva Itália
  (DAP 0 a 108). Em outra cultura (ex.: manga), a ETc, o balanço e a lâmina já saem com o Kc certo, mas a classe
  vem marcada como pouco confiável até o retreino com várias culturas.
- **Dias com a placa desligada** não são preenchidos: o histórico pula esses dias.
