# AgroEdge — estação completa (`main.py`)

O `main.py` lê todos os sensores, fecha o dia à meia-noite (hora local) e calcula:
ET0 (Penman-Monteith FAO-56) → ETc = Kc × ET0 → balanço hídrico → classificador → lâmina de irrigação.
Mostra os valores no display da BitDogLab e grava um resumo por dia em `diario.csv` na placa.

Com o `config_rede.py` (Wi-Fi e senha da placa), a estação também fala com a plataforma
(https://agroedge.tech) por MQTT com TLS: manda a telemetria e o fechamento do dia, recebe a
configuração do cultivo pelo painel e os comandos da válvula, e faz a irrigação automática.
Sem rede, continua igual e manda o atrasado quando a rede volta.

## Gravar a placa (o jeito fácil)

Na raiz do repositório, com a placa na USB (Python com o `mpremote`, como o do backend):

```bash
python firmware/preparar_placa.py --wifi "NomeDaRede" --gravar          # firmware completo
python firmware/preparar_placa.py --wifi "OutraRede" --so-rede --gravar # só trocar o Wi-Fi
python firmware/preparar_placa.py --serial agroedge-00003 --cadastrar --wifi "Rede" --gravar  # placa nova
```

O script pede a senha do Wi-Fi sem mostrar, busca a senha MQTT da placa na VPS pela chave SSH,
monta `firmware/para_a_placa/`, instala o `umqtt.simple` se faltar, grava e reinicia a placa.

**Na placa só muda o `config_rede.py` (o Wi-Fi).** A cultura, a data da poda/floração, o solo, a
vazão e a irrigação automática vêm do painel (Cultivos e Dispositivo) e ficam em
`config_plataforma.json`; os valores do `config_local.py` são só o padrão para usar sem rede.

## Pinos

| Sensor | Pino | Onde |
|---|---|---|
| AM2302 (T e UR) | GPIO17 | IDC, fileira "GND GP16 GP17 GND GP28 3V3 GND", 3º pino; VCC no 3V3, pull-up de 10 kΩ entre DATA e 3V3 |
| Piranômetro RS-485 | UART1 GPIO8 (TX→DI), GPIO9 (RX←RO, divisor 1k/2k), GPIO4 (DE+RE) | mesma fileira; sensor em 12 V |
| Anemômetro Met One 014A | GPIO18 | IDC, fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V", 1º pino; o outro fio no GND |
| Pluviômetro | GPIO16 | IDC, fileira "GND GP16 GP17 GND GP28 3V3 GND", 2º pino; o outro fio no GND |
| Relógio DS3231 (opcional) | I²C0: SDA GPIO0, SCL GPIO1, endereço 0x68 | conector I²C0; 3V3 |
| Display OLED | I²C1 GPIO14/15 | o da própria placa |

| Relé da válvula (módulo "low level") | GPIO19 | IDC, fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V", 2º pino; `RELE_NIVEL_BAIXO` no `config_local.py` |

Livre ainda: GPIO20.

## Arquivos para copiar para a placa
`main.py`, `config_local.py`, `culturas.py`, `eto.py`, `termohigro.py`, `relogio.py`, `anemometro.py`, `pluviometro.py`,
`piranometro.py`, `lamina.py`, `classificador.py`, `ssd1306.py` e os arquivos do classificador escolhido em
`config_local.MODELO`:
- `"v3_1"` (padrão): `historico_v3.py` e `agroedge_pesos_v3_1.py`;
- `"v1"` (só uva): `historico.py` e `agroedge_pesos.py`.
Para a plataforma: `conexao.py`, `valvula.py`, `config_rede.py` (gerado; fora do git),
`isrg_root_x2.der` (raiz do certificado, gerada do `isrg_root_x2.pem`) e a biblioteca
`umqtt.simple` (`mpremote mip install umqtt.simple`). O `preparar_placa.py` faz tudo isso.
Não copie `__pycache__`, `teste_main_pc.py` nem a pasta `bancada`.

O relógio interno e o DS3231 guardam a hora em **UTC** (o TLS exige); o `relogio.agora()` devolve
a hora local. Um DS3231 acertado antes desta versão (em hora local) fica 3 h errado até o primeiro
acerto pelo NTP, que acontece sozinho com o Wi-Fi.

## Antes de ligar no campo (`config_local.py`)
- `LATITUDE` e `ALTITUDE_M` do pomar (o GPS do celular dá os dois).
- `ANEMO_ALTURA_M`: altura real das conchas.
- Cultura (`CULTURA`: `uva_italia`, `manga_tommy_atkins` ou `manga_palmer`) e `DATA_REFERENCIA` (data da poda para a
  uva e a manga Palmer, do início da floração para a manga Tommy Atkins). Os dados de cada cultura (Kc, p, raiz e fontes) estão em `culturas.py`.
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
- **Classificador (padrão `MODELO = "v3_1"`):** serve para todas as culturas da biblioteca, inclusive a manga Palmer
  no ano todo. Precisa de duas informações no `config_local` (ou pelo painel): `FONTE_IRRIGACAO` (sensor, manual,
  tempo, parcial ou nenhuma) e `INICIO_USO` (ciclo, apos_irr ou meio). Com `FONTE_IRRIGACAO = "nenhuma"` a placa não
  mostra a classe nem a lâmina e pede o registro da irrigação. Com informação de irrigação, acertou ~88% nos testes
  simulados (`modelo/16_conferir_firmware_v3_1.py`). O `MODELO = "v1"` (só uva, dados completos) continua disponível.
- **Memória:** o `agroedge_pesos_v3_1.py` tem 1.661 números (6,6 KB em `array('f')`, ~22 KB de texto). Se a placa
  der `MemoryError` ao importar, pré-compile com o `mpy-cross` (gera `.mpy`, que ocupa bem menos RAM ao carregar).
- **Dias com a placa desligada** não são preenchidos: o histórico pula esses dias.
